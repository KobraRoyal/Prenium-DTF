from __future__ import annotations

import json
from json import JSONDecodeError

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from apps.notifications.services.workshop_push import (
    WorkshopNotificationService,
    WorkshopPushDisabled,
)
from apps.portal.views_common import StaffPortalMixin

workshop_notification_service = WorkshopNotificationService()


class StaffWorkshopPushPermissionMixin(StaffPortalMixin):
    required_permissions = (
        "orders.view_order",
        "production.view_productionjob",
    )

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and any(
            not request.user.has_perm(permission) for permission in self.required_permissions
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def _error_response(*, code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _read_json_body(request) -> dict[str, object]:
    payload = json.loads(request.body or b"{}")
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def _string_value(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


class StaffPushNotificationStateView(StaffWorkshopPushPermissionMixin, View):
    def get(self, request):
        state = workshop_notification_service.subscription_state(actor=request.user)
        return JsonResponse(
            {
                "ok": True,
                "enabled": state.enabled,
                "configured": state.configured,
                "vapid_public_key": state.vapid_public_key,
                "subscriptions": [
                    {
                        "public_id": item.public_id,
                        "last_seen_at": item.last_seen_at,
                    }
                    for item in state.subscriptions
                ],
            }
        )


class StaffPushNotificationSubscribeView(StaffWorkshopPushPermissionMixin, View):
    def post(self, request):
        try:
            payload = _read_json_body(request)
            subscription = workshop_notification_service.subscribe(
                actor=request.user,
                endpoint=_string_value(payload, "endpoint"),
                p256dh=_string_value(payload, "p256dh"),
                auth=_string_value(payload, "auth"),
                source="portal",
            )
        except (JSONDecodeError, UnicodeDecodeError, ValueError, ValidationError):
            return _error_response(
                code="invalid_subscription",
                message="Cet abonnement de notification n’est pas valide.",
                status=400,
            )
        except WorkshopPushDisabled:
            return _error_response(
                code="push_unavailable",
                message="Le service de notification n’est pas disponible.",
                status=503,
            )
        return JsonResponse(
            {
                "ok": True,
                "subscription": {"public_id": str(subscription.public_id)},
            },
            status=201,
        )


class StaffPushNotificationUnsubscribeView(StaffWorkshopPushPermissionMixin, View):
    def post(self, request, subscription_public_id):
        workshop_notification_service.unsubscribe(
            actor=request.user,
            subscription_public_id=subscription_public_id,
            source="portal",
        )
        return JsonResponse({"ok": True})


class StaffPushNotificationEventsView(StaffWorkshopPushPermissionMixin, View):
    def get(self, request):
        cursor = request.GET.get("cursor") or None
        try:
            page = workshop_notification_service.read_recent_events(
                actor=request.user,
                cursor=cursor,
            )
        except ValidationError:
            return _error_response(
                code="invalid_cursor",
                message="Le suivi des notifications doit être réinitialisé.",
                status=400,
            )
        if cursor and not page.events:
            return HttpResponse(status=204)
        return JsonResponse(
            {
                "ok": True,
                "cursor": page.cursor,
                "events": [
                    {
                        "public_id": item.public_id,
                        "created_at": item.created_at,
                    }
                    for item in page.events
                ],
            }
        )


@method_decorator(never_cache, name="dispatch")
class ServiceWorkerView(View):
    def get(self, request):
        response = render(request, "service-worker.js", content_type="application/javascript")
        response["Cache-Control"] = "no-store"
        response["Service-Worker-Allowed"] = "/"
        return response
