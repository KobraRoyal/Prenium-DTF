import pytest
from django.contrib.auth import authenticate, get_user_model


@pytest.mark.django_db
def test_user_model_uses_email_as_login_identifier():
    user = get_user_model().objects.create_user(
        email="contact@example.com",
        password="strong-password",
        first_name="Ada",
    )

    authenticated = authenticate(email="contact@example.com", password="strong-password")

    assert user.USERNAME_FIELD == "email"
    assert authenticated == user
    assert user.email == "contact@example.com"
