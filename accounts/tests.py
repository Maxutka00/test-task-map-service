from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.core.mail import BadHeaderError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from .models import OutgoingMail, User
from .tasks import deliver_next, deliver_pending_mail


class AccountTests(APITestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _csrf_client(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/csrf/")
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        return client

    def test_session_and_csrf(self):
        raw_client = APIClient(enforce_csrf_checks=True)
        account = {
            "username": "reader",
            "email": "reader@example.com",
            "password": "qweRty_98124",
        }

        missing_csrf = raw_client.post("/api/auth/register/", account)
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(missing_csrf["Content-Type"], "application/json")

        raw_client.get("/api/auth/csrf/")
        raw_client.credentials(HTTP_X_CSRFTOKEN=raw_client.cookies["csrftoken"].value)

        self.assertEqual(raw_client.post("/api/auth/register/", account).status_code, 201)
        self.assertEqual(raw_client.post("/api/auth/login/", account).status_code, 200)

        raw_client.credentials()
        self.assertEqual(raw_client.post("/api/auth/logout/").status_code, 403)

        raw_client.credentials(HTTP_X_CSRFTOKEN=raw_client.cookies["csrftoken"].value)
        self.assertEqual(raw_client.post("/api/auth/logout/").status_code, 204)

    def test_unicode_username_on_register_and_login(self):
        client = self._csrf_client()
        fullwidth_name = "Ｍaria"
        password = "mAria_login771"

        reg = client.post(
            "/api/auth/register/",
            {"username": fullwidth_name, "email": "maria@example.com", "password": password},
        )
        self.assertEqual(reg.status_code, 201)
        self.assertEqual(reg.data["username"], "Maria")

        dup = client.post(
            "/api/auth/register/",
            {"username": fullwidth_name, "email": "other@example.com", "password": password},
        )
        self.assertEqual(dup.status_code, 400)
        self.assertIn("username", dup.data)

        login_fullwidth = client.post(
            "/api/auth/login/",
            {"username": fullwidth_name, "password": password},
        )
        self.assertEqual(login_fullwidth.status_code, 200)
        self.assertEqual(login_fullwidth.data["username"], "Maria")

        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(client.post("/api/auth/logout/").status_code, 204)

        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        login_ascii = client.post(
            "/api/auth/login/",
            {"username": "Maria", "password": password},
        )
        self.assertEqual(login_ascii.status_code, 200)

    def test_password_reset_and_cooldown(self):
        user = User.objects.create_user("traveler", "traveler@example.com", "oldPass_44192")
        client = APIClient()

        self.assertEqual(client.post("/api/auth/password/reset/", {"email": "nobody@example.com"}).status_code, 202)
        self.assertEqual(client.post("/api/auth/password/reset/", {"email": user.email}).status_code, 202)
        self.assertEqual(client.post("/api/auth/password/reset/", {"email": user.email}).status_code, 202)
        self.assertEqual(OutgoingMail.objects.count(), 1)

        message = OutgoingMail.objects.get()
        token = message.body.split("token: ")[1].splitlines()[0]
        new_password = "newPass_88310"
        payload = {"uid": user.pk, "token": token, "password": new_password}

        self.assertEqual(client.post("/api/auth/password/reset/confirm/", payload).status_code, 204)
        self.assertEqual(client.post("/api/auth/password/reset/confirm/", payload).status_code, 400)

        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))

    def test_password_length_limit_and_login_throttle(self):
        client = self._csrf_client()
        resp = client.post(
            "/api/auth/register/",
            {"username": "longpass", "email": "long@example.com", "password": "a" * 200},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.data)

        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "2/minute"}):
            creds = {"username": "missing", "password": "wrong_pass_123"}
            self.assertEqual(client.post("/api/auth/login/", creds).status_code, 400)
            self.assertEqual(client.post("/api/auth/login/", creds).status_code, 400)
            self.assertEqual(client.post("/api/auth/login/", creds).status_code, 429)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_mail_retry_and_bad_header(self):
        first = OutgoingMail.objects.create(recipient="user@example.com", subject="Review", body="Text")
        with patch("accounts.tasks.send_mail", side_effect=OSError("SMTP offline")):
            self.assertTrue(deliver_next())

        first.refresh_from_db()
        self.assertEqual(first.attempts, 1)
        self.assertIsNone(first.sent_at)
        self.assertFalse(deliver_next())

        first.available_at = timezone.now()
        first.save(update_fields=["available_at"])
        self.assertTrue(deliver_next())
        self.assertEqual(len(mail.outbox), 1)

        broken = OutgoingMail.objects.create(recipient="bad@example.com", subject="Bad", body="Token")
        valid = OutgoingMail.objects.create(recipient="ok@example.com", subject="Good", body="Hello")

        real_send = mail.send_mail

        def side_effect(subject, body, from_email, recipient_list, *args, **kwargs):
            if recipient_list == ["bad@example.com"]:
                raise BadHeaderError("Invalid header")
            return real_send(subject, body, from_email, recipient_list, *args, **kwargs)

        with patch("accounts.tasks.send_mail", side_effect=side_effect):
            deliver_pending_mail()

        broken.refresh_from_db()
        valid.refresh_from_db()
        self.assertIsNone(broken.available_at)
        self.assertEqual(broken.body, "")
        self.assertIn("Invalid header", broken.last_error)
        self.assertIsNotNone(valid.sent_at)
        self.assertEqual(len(mail.outbox), 2)
