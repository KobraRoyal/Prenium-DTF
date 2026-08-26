import pytest
from apps.auditlog.models import AuditLogEntry
from apps.branding.forms import BrandThemeSettingsForm
from apps.branding.models import BrandThemeSettings
from apps.branding.services import (
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLOR,
    BrandThemeService,
    build_brand_theme,
    contrast_ratio,
)
from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from rest_framework.test import APIClient


def _permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(
        content_type__app_label=app_label,
        codename=codename,
    )


def _staff_user(*, email: str, view_brand: bool = False, change_brand: bool = False):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(_permission("accounts", "access_staff_portal"))
    if view_brand:
        user.user_permissions.add(_permission("branding", "view_brandthemesettings"))
    if change_brand:
        user.user_permissions.add(_permission("branding", "change_brandthemesettings"))
    return user


def _client_user(*, email: str, customer_name: str, role=CustomerMembership.Role.OWNER):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=customer_name)
    CustomerMembership.objects.create(customer=customer, user=user, role=role)
    return user


@pytest.mark.django_db
def test_effective_theme_falls_back_to_warm_light_palette_without_creating_row():
    theme = BrandThemeService().get_effective_theme()

    assert BrandThemeSettings.objects.count() == 0
    assert theme.primary == DEFAULT_PRIMARY_COLOR
    assert theme.primary_strong == "#E65944"
    assert theme.secondary == DEFAULT_SECONDARY_COLOR
    assert theme.secondary_strong == "#770176"
    assert theme.paper == "#F4F0E6"
    assert theme.ink == "#1A1815"
    assert contrast_ratio(theme.primary, theme.primary_ink) >= 4.5
    assert contrast_ratio(theme.secondary, theme.secondary_ink) >= 4.5


@pytest.mark.django_db
def test_brand_form_normalizes_hex_and_rejects_css_injection_and_duplicate_colors():
    valid = BrandThemeSettingsForm(data={"primary_color": "#ff8775", "secondary_color": "#a83bc4"})
    assert valid.is_valid(), valid.errors
    assert valid.cleaned_data["primary_color"] == "#FF8775"
    assert valid.cleaned_data["secondary_color"] == "#A83BC4"

    injected = BrandThemeSettingsForm(
        data={"primary_color": "red;}</style>", "secondary_color": "#A83BC4"}
    )
    assert not injected.is_valid()

    duplicate = BrandThemeSettingsForm(
        data={"primary_color": "#FF8775", "secondary_color": "#ff8775"}
    )
    assert not duplicate.is_valid()
    assert "secondary_color" in duplicate.errors

    model = BrandThemeSettings(primary_color="#123456", secondary_color="#123456")
    with pytest.raises(ValidationError):
        model.full_clean()


@pytest.mark.django_db
def test_brand_service_rechecks_permission_versions_and_audits_changes():
    viewer = _staff_user(email="brand-viewer@example.com", view_brand=True)
    manager = _staff_user(
        email="brand-manager@example.com",
        view_brand=True,
        change_brand=True,
    )
    service = BrandThemeService()

    with pytest.raises(PermissionDenied):
        service.update(
            primary_color="#F06755",
            secondary_color="#713B9C",
            actor=viewer,
            source="test",
        )

    first = service.update(
        primary_color="#f06755",
        secondary_color="#713b9c",
        actor=manager,
        source="test",
        ip_address="127.0.0.42",
    )
    assert first.primary_color == "#F06755"
    assert first.secondary_color == "#713B9C"
    assert first.version == 1

    second = service.update(
        primary_color="#E95D4D",
        secondary_color="#66318B",
        actor=manager,
        source="test",
    )
    assert second.pk == first.pk
    assert second.version == 2

    events = AuditLogEntry.objects.filter(
        action="branding.theme.updated",
        target_public_id=second.public_id,
    ).order_by("created_at")
    assert events.count() == 2
    assert events.first().ip_address == "127.0.0.42"
    assert events.last().metadata == {
        "scope": "global",
        "source": "test",
        "before": {
            "theme_key": "octostitch_light",
            "primary_color": "#F06755",
            "secondary_color": "#713B9C",
            "version": 1,
        },
        "after": {
            "theme_key": "octostitch_light",
            "primary_color": "#E95D4D",
            "secondary_color": "#66318B",
            "version": 2,
        },
    }


@pytest.mark.django_db
def test_brand_settings_route_separates_staff_view_and_change_permissions():
    url = reverse("portal:staff-brand-settings")
    client_user = _client_user(
        email="brand-client-admin@example.com",
        customer_name="Client sans droit Atelier",
        role=CustomerMembership.Role.ADMIN,
    )
    staff_without_brand = _staff_user(email="brand-staff@example.com")
    viewer = _staff_user(email="brand-view-only@example.com", view_brand=True)
    manager = _staff_user(
        email="brand-admin@example.com",
        view_brand=True,
        change_brand=True,
    )
    client = APIClient()

    assert client.get(url).status_code == 302

    assert client.login(email=client_user.email, password="pass") is True
    assert client.get(url).status_code == 403
    client.logout()

    assert client.login(email=staff_without_brand.email, password="pass") is True
    assert client.get(url).status_code == 403
    client.logout()

    assert client.login(email=viewer.email, password="pass") is True
    viewer_html = client.get(url).content.decode()
    assert "Identité visuelle" in viewer_html
    assert "seul un administrateur Atelier peut la modifier" in viewer_html
    assert (
        client.post(
            url,
            {"primary_color": "#F06755", "secondary_color": "#713B9C"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            url,
            {"primary_color": "not-a-color", "secondary_color": "#713B9C"},
        ).status_code
        == 403
    )
    assert BrandThemeSettings.objects.count() == 0
    client.logout()

    assert client.login(email=manager.email, password="pass") is True
    response = client.post(
        url,
        {"primary_color": "#F06755", "secondary_color": "#713B9C"},
        REMOTE_ADDR="192.0.2.20",
    )
    assert response.status_code == 302
    row = BrandThemeSettings.objects.get(singleton_key=1)
    assert row.updated_by == manager
    assert row.primary_color == "#F06755"
    assert row.secondary_color == "#713B9C"
    assert AuditLogEntry.objects.get(action="branding.theme.updated").ip_address == "192.0.2.20"


@pytest.mark.django_db
def test_global_theme_reaches_public_client_and_atelier_without_exposing_settings_metadata():
    manager = _staff_user(
        email="brand-global-manager@example.com",
        view_brand=True,
        change_brand=True,
    )
    client_a = _client_user(email="brand-a@example.com", customer_name="Marque A")
    client_b = _client_user(email="brand-b@example.com", customer_name="Marque B")
    BrandThemeService().update(
        primary_color="#E75F50",
        secondary_color="#64328C",
        actor=manager,
        source="test",
    )
    row = BrandThemeSettings.objects.get()
    expected_tokens = "--brand: #E75F50"
    expected_secondary = "--accent: #64328C"
    browser = APIClient()

    public_html = browser.get(reverse("home")).content.decode()
    assert expected_tokens in public_html
    assert expected_secondary in public_html

    for user in (client_a, client_b):
        assert browser.login(email=user.email, password="pass") is True
        html = browser.get(reverse("portal:client-dashboard")).content.decode()
        assert expected_tokens in html
        assert expected_secondary in html
        assert str(row.public_id) not in html
        assert manager.email not in html
        browser.logout()

    assert browser.login(email=manager.email, password="pass") is True
    atelier_html = browser.get(reverse("portal:staff-dashboard")).content.decode()
    assert expected_tokens in atelier_html
    assert expected_secondary in atelier_html
    assert str(row.public_id) not in atelier_html


@pytest.mark.django_db
def test_brand_settings_restore_reinstates_default_palette():
    manager = _staff_user(
        email="brand-restore@example.com",
        view_brand=True,
        change_brand=True,
    )
    client = APIClient()
    assert client.login(email=manager.email, password="pass") is True
    url = reverse("portal:staff-brand-settings")

    client.post(url, {"primary_color": "#E75F50", "secondary_color": "#64328C"})
    response = client.post(url, {"intent": "restore"})

    assert response.status_code == 302
    row = BrandThemeSettings.objects.get()
    assert row.primary_color == DEFAULT_PRIMARY_COLOR
    assert row.secondary_color == DEFAULT_SECONDARY_COLOR
    assert row.version == 2


def test_custom_palette_derives_readable_action_text():
    dark_theme = build_brand_theme(primary="#111111", secondary="#222222")
    light_theme = build_brand_theme(primary="#FAFAFA", secondary="#EEEEEE")

    assert dark_theme.primary_ink == "#FFFFFF"
    assert light_theme.primary_ink == "#000000"
    assert contrast_ratio(dark_theme.primary, dark_theme.primary_ink) >= 4.5
    assert contrast_ratio(light_theme.primary, light_theme.primary_ink) >= 4.5
