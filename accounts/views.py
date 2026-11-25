from datetime import timedelta

from django.contrib.auth import login, logout, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OutgoingMail, User
from .serializers import (
    LoginSerializer,
    RegistrationSerializer,
    ResetConfirmSerializer,
    ResetRequestSerializer,
)

RESET_EMAIL_COOLDOWN = timedelta(seconds=60)


def enforce_csrf(request):
    SessionAuthentication().enforce_csrf(request._request)


class CSRFTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request._request)})


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "register"

    def post(self, request):
        enforce_csrf(request)
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError({"detail": "Username or email is already registered."})
        return Response(serializer.data, status=201)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        enforce_csrf(request)
        serializer = LoginSerializer(data=request.data, context={"request": request._request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request._request, user)
        return Response({"id": user.pk, "username": user.username})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request._request)
        return Response(status=204)


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = ResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user and user.has_usable_password():
            cutoff = timezone.now() - RESET_EMAIL_COOLDOWN
            recently_requested = OutgoingMail.objects.filter(
                recipient__iexact=user.email,
                subject="Password reset",
                created_at__gte=cutoff,
            ).exists()
            if not recently_requested:
                token = default_token_generator.make_token(user)
                OutgoingMail.objects.create(
                    recipient=user.email,
                    subject="Password reset",
                    body=(
                        "POST /api/auth/password/reset/confirm/\n"
                        f"uid: {user.pk}\n"
                        f"token: {token}\n"
                        "Include your new password in the password field."
                    ),
                )
        return Response(status=202)


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    @transaction.atomic
    def post(self, request):
        serializer = ResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.select_for_update().filter(pk=data["uid"], is_active=True).first()
        if not default_token_generator.check_token(user, data["token"]):
            raise ValidationError({"detail": "Invalid or expired password reset token."})

        try:
            password_validation.validate_password(data["password"], user)
        except DjangoValidationError as exc:
            raise ValidationError({"password": exc.messages})

        user.set_password(data["password"])
        user.save(update_fields=["password"])
        return Response(status=204)
