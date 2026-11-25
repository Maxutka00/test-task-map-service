from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Avg, Case, Count, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, Ln
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class LocationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)

    def with_metrics(self):
        recent_cutoff = timezone.now() - timedelta(days=7)
        recent_views = (
            LocationView.objects.filter(location_id=OuterRef("pk"), viewed_at__gt=recent_cutoff)
            .values("location_id")
            .annotate(
                weight=Sum(
                    Case(
                        When(is_guest=True, then=Value(0.3)),
                        default=Value(1.0),
                    )
                )
            )
        )
        return self.annotate(
            rating=Avg("reviews__rating"),
            review_count=Count("reviews"),
            weighted_views=Coalesce(Subquery(recent_views.values("weight")), 0.0),
        ).annotate(
            popularity=Coalesce(F("rating"), 0.0) * Ln(1.0 + F("review_count")) + Ln(1.0 + F("weighted_views"))
        )


class Location(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    address = models.CharField(max_length=300)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = LocationQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(latitude__range=(-90, 90)), name="valid_latitude"),
            models.CheckConstraint(condition=Q(longitude__range=(-180, 180)), name="valid_longitude"),
        ]
        indexes = [
            models.Index(
                fields=["-created_at"],
                condition=Q(deleted_at__isnull=True),
                name="active_locations_created_idx",
            ),
        ]

    def __str__(self):
        return self.title


class LocationView(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(default=timezone.now)
    is_guest = models.BooleanField()

    class Meta:
        indexes = [
            models.Index(fields=["location", "viewed_at"]),
        ]

    def __str__(self):
        kind = "guest" if self.is_guest else "user"
        return f"Location #{self.location_id} ({kind})"


class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["location", "user"], name="one_location_subscription"),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.location_id}"
