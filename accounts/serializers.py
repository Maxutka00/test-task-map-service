from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import User

MAX_PASSWORD_LENGTH = 128


class NormalizedUsernameField(serializers.CharField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            data = User.normalize_username(data)
        return super().to_internal_value(data)


class RegistrationSerializer(serializers.ModelSerializer):
    username = NormalizedUsernameField(
        max_length=150,
        validators=[
            UnicodeUsernameValidator(),
            UniqueValidator(
                queryset=User.objects.all(),
                message="A user with that username already exists.",
            ),
        ],
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=MAX_PASSWORD_LENGTH,
    )

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("This email is already registered.")
        return normalized

    def validate(self, attrs):
        candidate = User(username=attrs["username"], email=attrs["email"])
        password_validation.validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = NormalizedUsernameField(max_length=150)
    password = serializers.CharField(
        trim_whitespace=False,
        write_only=True,
        max_length=MAX_PASSWORD_LENGTH,
    )

    def validate(self, attrs):
        user = authenticate(
            self.context["request"],
            username=attrs["username"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Invalid username or password.")
        return {"user": user}


class ResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ResetConfirmSerializer(serializers.Serializer):
    uid = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    token = serializers.CharField(max_length=128)
    password = serializers.CharField(
        trim_whitespace=False,
        write_only=True,
        max_length=MAX_PASSWORD_LENGTH,
    )
