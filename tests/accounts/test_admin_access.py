import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_superuser_can_access_admin_index():
    superuser = get_user_model().objects.create_superuser(
        email="admin@example.com",
        password="pass",
    )
    client = APIClient()
    client.force_login(superuser)

    response = client.get(reverse("admin:index"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_staff_user_without_superuser_should_not_access_admin_index():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    client = APIClient()
    client.force_login(staff_user)

    response = client.get(reverse("admin:index"))

    assert response.status_code == 302
    assert reverse("admin:login") in response.url
