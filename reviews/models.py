from django.conf import settings
from django.db import models
from django.db.models import Q

from locations.models import Location


class Review(models.Model):
    location = models.ForeignKey(Location, related_name="reviews", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["location", "author"], name="one_review_per_author"),
            models.CheckConstraint(condition=Q(rating__range=(1, 5)), name="valid_review_rating"),
        ]
        indexes = [
            models.Index(fields=["location", "-created_at"], name="review_loc_created_idx"),
        ]

    def __str__(self):
        return f"Review #{self.pk} ({self.rating}/5)"


class Vote(models.Model):
    class Value(models.TextChoices):
        LIKE = "like"
        DISLIKE = "dislike"

    review = models.ForeignKey(Review, related_name="votes", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    value = models.CharField(max_length=7, choices=Value.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["review", "user"], name="one_vote_per_user"),
            models.CheckConstraint(condition=Q(value__in=["like", "dislike"]), name="valid_vote"),
        ]

    def __str__(self):
        return f"{self.user_id}: {self.value} on review #{self.review_id}"
