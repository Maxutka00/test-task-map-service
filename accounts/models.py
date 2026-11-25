from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class AccountUserManager(UserManager):
    def get_by_natural_key(self, username):
        normalized = self.model.normalize_username(username)
        return super().get_by_natural_key(normalized)


class User(AbstractUser):
    email = models.EmailField(unique=True)

    objects = AccountUserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="user_email_case_insensitive"),
        ]

    def __str__(self):
        return self.username


class OutgoingMail(models.Model):
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    available_at = models.DateTimeField(default=timezone.now, null=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    def __str__(self):
        return f"{self.recipient}: {self.subject}"
