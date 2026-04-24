from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import BaseModel

from .managers import UserManager


class User(BaseModel, AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    staff_mfa_required = models.BooleanField(default=False)
    staff_mfa_enabled = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ("email",)
        permissions = [
            ("access_staff_portal", "Can access the staff portal"),
        ]

    def __str__(self) -> str:
        return self.email
