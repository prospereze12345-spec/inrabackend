import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from apps.accounts.managers import UserManager


class CountryChoice(models.TextChoices):
    NIGERIA = "NG", "Nigeria"
    KENYA = "KE", "Kenya"
    GHANA = "GH", "Ghana"
    SOUTH_AFRICA = "ZA", "South Africa"
    EGYPT = "EG", "Egypt"
    OTHER = "OTHER", "Other"

class User(AbstractBaseUser, PermissionsMixin):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email       = models.EmailField(unique=True, db_index=True)
    full_name   = models.CharField(max_length=255)
    country = models.CharField(max_length=10, choices=CountryChoice.choices, default=CountryChoice.OTHER)
    is_verified = models.BooleanField(default=False)
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    created_at  = models.DateTimeField(default=timezone.now)
    updated_at  = models.DateTimeField(auto_now=True)

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["full_name"]
    objects = UserManager()

    class Meta:
        db_table = "accounts_user"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"