import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.test import APIClient, APITransactionTestCase

from accounts.models import User
from reviews.models import Review

from .models import Category, Location, LocationView
from .traffic import admit_guest, redis


class CatalogTests(APITransactionTestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("guide", "guide@example.com")
        self.reader = User.objects.create_user("reader", "reader@example.com")
        self.category = Category.objects.create(name="Parks")
        self.fields = {
            "title": "Park",
            "category": self.category.pk,
            "address": "Hill, 2",
            "latitude": "50.100000",
            "longitude": "30.210000",
            "description": "Старий міський парк",
        }
        self.client.force_authenticate(self.owner)
        response = self.client.post("/api/locations/", self.fields)
        self.assertEqual(response.status_code, 201, response.content)
        self.location = Location.objects.get(pk=response.data["id"])
        self.url = f"/api/locations/{self.location.pk}/"

    def tearDown(self):
        prefix = f"{connection.settings_dict['NAME']}:"
        keys = list(redis.scan_iter(match=f"{prefix}*"))
        if keys:
            redis.delete(*keys)
        cache.clear()

    def test_permissions_and_soft_delete(self):
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.patch(self.url, {"title": "Hill"}).status_code, 403)
        self.assertEqual(self.client.delete(self.url).status_code, 403)
        self.assertEqual(self.client.post("/api/categories/", {"name": "Lakes"}).status_code, 403)

        self.reader.is_staff = True
        self.reader.save()

        self.assertEqual(self.client.patch(self.url, {"latitude": "91"}).status_code, 400)
        self.assertEqual(self.client.delete(self.url).status_code, 204)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(self.url + "reviews/").status_code, 404)
        self.assertEqual(self.client.get("/api/locations/export/").data, [])
        self.assertIsNotNone(Location.objects.get(pk=self.location.pk).deleted_at)
        self.assertEqual(self.client.delete(f"/api/categories/{self.category.pk}/").status_code, 409)

    def test_metrics_filter_cache_and_export(self):
        now = timezone.now()
        LocationView.objects.bulk_create([
            LocationView(location=self.location, is_guest=True),
            LocationView(location=self.location, is_guest=True),
            LocationView(location=self.location, is_guest=False),
            LocationView(location=self.location, is_guest=False, viewed_at=now - timedelta(days=7)),
        ])
        Review.objects.create(location=self.location, author=self.owner, rating=3, comment="Nice")

        listing = "/api/locations/?search=парк&min_rating=3&ordering=-popularity"
        before = self.client.get(listing).data["results"][0]
        self.assertAlmostEqual(before["popularity"], 3 * math.log(2) + math.log(2.6))

        self.client.force_authenticate(self.reader)
        review = self.client.post(self.url + "reviews/", {"rating": 5, "comment": "Great"})
        self.assertEqual(review.status_code, 201)

        after = self.client.get(listing).data["results"][0]
        self.assertEqual((after["rating"], after["review_count"]), (4, 2))
        self.assertAlmostEqual(after["popularity"], 4 * math.log(3) + math.log(2.6))

        third_user = User.objects.create_user("visitor", "visitor@example.com")
        Review.objects.create(location=self.location, author=third_user, rating=5, comment="Good")
        cache.clear()

        detail = self.client.get(self.url).data
        exact_filtered = self.client.get(f"/api/locations/?rating={detail['rating']}").data
        self.assertEqual(exact_filtered["count"], 1)

        missing_author = self.client.get("/api/locations/?author=999999")
        self.assertEqual(missing_author.status_code, 200)
        self.assertEqual(missing_author.data["count"], 0)

        csv_resp = self.client.get("/api/locations/export/?format=csv&min_rating=4")
        row, = csv.DictReader(io.StringIO(csv_resp.content.decode()))
        self.assertEqual(row["address"], "Hill, 2")

        Review.objects.filter(author=third_user).delete()
        self.client.delete(f"/api/reviews/{review.data['id']}/")
        self.assertEqual(self.client.get(listing).data["results"][0]["rating"], 3)

    def test_coordinates_rounding_and_csv_escaping(self):
        payload = {
            **self.fields,
            "title": "=SUM(1,2)",
            "latitude": 50.4501004,
            "longitude": -30.5234006,
        }
        created = self.client.post("/api/locations/", payload)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["latitude"], "50.450100")
        self.assertEqual(created.data["longitude"], "-30.523401")

        csv_resp = self.client.get("/api/locations/export/?format=csv&search=SUM")
        row, = csv.DictReader(io.StringIO(csv_resp.content.decode()))
        self.assertEqual(row["title"], "'=SUM(1,2)")
        self.assertEqual(row["longitude"], "-30.523401")

    def test_export_includes_second_page(self):
        Location.objects.bulk_create([
            Location(
                title=f"Spot {i}",
                description="Point",
                category=self.category,
                address="Main St",
                author=self.owner,
                latitude=1,
                longitude=1,
            )
            for i in range(20)
        ])
        self.assertEqual(len(self.client.get("/api/locations/").data["results"]), 20)
        self.assertEqual(len(self.client.get("/api/locations/?page=2").data["results"]), 1)
        self.assertEqual(len(self.client.get("/api/locations/export/?page=2").data), 21)

    def test_guest_view_with_ip_change(self):
        guest_client = APIClient()
        ip_one = "198.51.100.10"
        ip_two = "203.0.113.25"

        first = guest_client.get(self.url, REMOTE_ADDR=ip_one)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(LocationView.objects.count(), 1)

        second = guest_client.get(self.url, REMOTE_ADDR=ip_two)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(LocationView.objects.count(), 1)

        session_key = guest_client.cookies["sessionid"].value
        guest_hash = salted_hmac("guest-session", session_key).hexdigest()
        guest_key = f"{connection.settings_dict['NAME']}:views:{self.location.pk}:guest:{guest_hash}"
        redis.delete(guest_key)

        after_expiry = guest_client.get(self.url, REMOTE_ADDR=ip_two)
        self.assertEqual(after_expiry.status_code, 200)
        self.assertEqual(LocationView.objects.count(), 2)

    def test_guest_limit_by_ip_and_location(self):
        address = f"2001:db8::{uuid4().hex[:4]}"
        prefix = f"{connection.settings_dict['NAME']}:views:{self.location.pk}"
        ip_key = f"{prefix}:ip:{salted_hmac('guest-ip', address).hexdigest()}"

        for _ in range(49):
            token = uuid4().hex
            self.assertEqual(admit_guest(keys=[f"{prefix}:guest:{token}", ip_key], args=[token]), 1)

        def try_admit(idx):
            token = f"c-{idx}-{uuid4().hex}"
            return admit_guest(keys=[f"{prefix}:guest:{token}", ip_key], args=[token])

        with ThreadPoolExecutor(max_workers=5) as pool:
            admitted = list(pool.map(try_admit, range(5)))
        self.assertEqual(sum(admitted), 1)

        blocked_client = APIClient()
        self.assertEqual(blocked_client.get(self.url, REMOTE_ADDR=address).status_code, 200)
        self.assertNotIn("sessionid", blocked_client.cookies)
        self.assertEqual(LocationView.objects.count(), 0)

        seconds, _ = redis.time()
        redis.zadd(ip_key, {"expired": (seconds - 3601) * 1000})
        redis.zpopmax(ip_key)

        fresh_client = APIClient()
        self.assertEqual(fresh_client.get(self.url, REMOTE_ADDR=address).status_code, 200)
        self.assertEqual(fresh_client.get(self.url, REMOTE_ADDR=address).status_code, 200)
        self.assertEqual(LocationView.objects.count(), 1)
        self.assertEqual(redis.zcard(ip_key), 50)

        other_id = self.client.post("/api/locations/", self.fields).data["id"]
        self.assertEqual(fresh_client.get(f"/api/locations/{other_id}/", REMOTE_ADDR=address).status_code, 200)
        self.assertEqual(LocationView.objects.count(), 2)

    def test_authenticated_view_once_per_hour(self):
        key = f"{connection.settings_dict['NAME']}:views:{self.location.pk}:user:{self.owner.pk}"
        redis.delete(key)

        for _ in range(2):
            self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(LocationView.objects.count(), 1)
        self.assertGreater(redis.ttl(key), 3590)

        redis.pexpireat(key, 1)
        self.client.get(self.url)
        self.assertEqual(LocationView.objects.count(), 2)
