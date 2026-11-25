from datetime import timedelta
from smtplib import SMTPException

from celery import shared_task
from django.conf import settings
from django.core.mail import BadHeaderError, send_mail
from django.db import transaction
from django.utils import timezone

from .models import OutgoingMail

MAX_DELIVERY_ATTEMPTS = 8
BASE_RETRY_SECONDS = 30
RETENTION_DAYS = 7


def _retry_delay(attempt_number):
    return timedelta(seconds=BASE_RETRY_SECONDS * (2 ** (attempt_number - 1)))


def deliver_next():
    # Спочатку короткою транзакцією резервуємо лист із часовим запасом,
    # щоб не тримати блокування рядка в БД під час виклику SMTP.
    with transaction.atomic():
        now = timezone.now()
        message = (
            OutgoingMail.objects.select_for_update(skip_locked=True)
            .filter(sent_at__isnull=True, available_at__lte=now)
            .order_by("available_at", "pk")
            .first()
        )
        if message is None:
            return False

        message.attempts += 1
        delay = _retry_delay(message.attempts)
        if message.attempts < MAX_DELIVERY_ATTEMPTS:
            message.available_at = now + delay
        else:
            message.available_at = None
        message.save(update_fields=["attempts", "available_at"])

    try:
        send_mail(
            message.subject,
            message.body,
            settings.DEFAULT_FROM_EMAIL,
            [message.recipient],
        )
    except (BadHeaderError, ValueError) as exc:
        message.available_at = None
        message.body = ""
        message.last_error = str(exc)
        message.save(update_fields=["available_at", "body", "last_error"])
    except (OSError, SMTPException) as exc:
        message.last_error = str(exc)
        if message.attempts < MAX_DELIVERY_ATTEMPTS:
            message.available_at = timezone.now() + delay
            message.save(update_fields=["available_at", "last_error"])
        else:
            message.available_at = None
            message.body = ""
            message.save(update_fields=["available_at", "body", "last_error"])
    else:
        message.sent_at = timezone.now()
        message.available_at = None
        message.body = ""
        message.last_error = ""
        message.save(update_fields=["sent_at", "available_at", "body", "last_error"])

    return True


@shared_task
def deliver_pending_mail():
    for _ in range(50):
        if not deliver_next():
            break


@shared_task
def cleanup_old_records():
    from locations.models import LocationView

    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    LocationView.objects.filter(viewed_at__lt=cutoff).delete()
    OutgoingMail.objects.filter(sent_at__lt=cutoff).delete()
