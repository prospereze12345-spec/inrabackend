from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from apps.accounts.models import CountryChoice


class SignupSerializer(serializers.Serializer):
    full_name        = serializers.CharField(min_length=2, max_length=255, trim_whitespace=True)
    email            = serializers.EmailField()
    country          = serializers.ChoiceField(choices=CountryChoice.choices)
    password         = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.lower().strip()

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()


class VerifyTokenSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=1, max_length=200, trim_whitespace=True)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(min_length=1)


class UserProfileSerializer(serializers.Serializer):
    id          = serializers.UUIDField()
    email       = serializers.EmailField()
    full_name   = serializers.CharField()
    country     = serializers.CharField()
    is_verified = serializers.BooleanField()
    created_at  = serializers.DateTimeField()