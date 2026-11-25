from concurrent.futures import ThreadPoolExecutor

from django.core.cache import cache
from django.db import close_old_connections, connections
from rest_framework.test import APIClient, APITransactionTestCase

from accounts.models import OutgoingMail, User
from locations.models import Category, Location

from .models import Review


class ReviewTests(APITransactionTestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("owner", "owner@example.com")
        self.author = User.objects.create_user("author", "author@example.com")
        self.subscriber = User.objects.create_user("watcher", "watcher@example.com")
        self.inactive = User.objects.create_user("disabled", "disabled@example.com", is_active=False)
        self.location = Location.objects.create(
            title="Square",
            description="Center",
            address="Square, 1",
            category=Category.objects.create(name="Places"),
            author=self.owner,
            latitude=0,
            longitude=0,
        )
        self.url = f"/api/locations/{self.location.pk}/"
        self.client.force_authenticate(self.author)

    def tearDown(self):
        cache.clear()

    def test_review_vote_and_notification_lifecycle(self):
        subscription_url = self.url + "subscription/"

        self.client.put(subscription_url)
        self.client.force_authenticate(self.subscriber)
        self.client.put(subscription_url)
        self.location.subscription_set.create(user=self.inactive)

        self.client.force_authenticate(self.author)
        payload = {"rating": 4, "comment": "Quiet"}
        response = self.client.post(self.url + "reviews/", payload)
        self.assertEqual(response.status_code, 201)

        self.assertCountEqual(
            OutgoingMail.objects.values_list("recipient", flat=True),
            [self.owner.email, self.subscriber.email],
        )
        self.assertEqual(self.client.post(self.url + "reviews/", payload).status_code, 409)

        detail_url = f"/api/reviews/{response.data['id']}/"
        vote_url = detail_url + "vote/"
        for value in ("like", "like", "dislike"):
            self.assertEqual(self.client.put(vote_url, {"value": value}).status_code, 200)

        review_item = self.client.get(self.url + "reviews/").data["results"][0]
        self.assertEqual((review_item["likes"], review_item["dislikes"]), (0, 1))

        self.assertEqual(self.client.delete(vote_url).status_code, 204)
        self.assertEqual(self.client.get(self.url + "reviews/").data["results"][0]["dislikes"], 0)

        self.client.force_authenticate(self.subscriber)
        self.assertEqual(self.client.delete(subscription_url).status_code, 204)

        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.delete(detail_url).status_code, 204)
        self.assertEqual(self.client.post(self.url + "reviews/", payload).status_code, 201)

        self.assertEqual(OutgoingMail.objects.filter(recipient=self.subscriber.email).count(), 1)
        self.assertEqual(OutgoingMail.objects.filter(recipient=self.owner.email).count(), 2)

    def test_concurrent_reviews(self):
        def post_review(_):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.author)
                return client.post(self.url + "reviews/", {"rating": 3, "comment": "Ok"}).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(post_review, range(2)))

        self.assertCountEqual(statuses, [201, 409])
        self.assertEqual(Review.objects.count(), 1)
        self.assertEqual(OutgoingMail.objects.count(), 1)
