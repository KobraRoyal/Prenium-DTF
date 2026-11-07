"""Prévisualisation et handlers HTTP 404 / 500 — shell auth Operate."""

from __future__ import annotations

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views import View


def _http_error_preview_allowed(request) -> bool:
    if settings.DEBUG:
        return True
    module = getattr(settings, "SETTINGS_MODULE", "") or ""
    # Dev local met parfois DEBUG=False pour tester les handlers custom.
    if module.endswith(".dev"):
        return True
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_staff)


class HttpErrorPreviewView(View):
    """Rendu des pages d’erreur custom — DEBUG, settings.dev, ou staff."""

    http_method_names = ["get"]
    status_code = 404
    template_name = "404.html"

    def get(self, request, *args, **kwargs):
        if not _http_error_preview_allowed(request):
            raise Http404()
        response = render(request, self.template_name)
        response.status_code = self.status_code
        return response


class Http404PreviewView(HttpErrorPreviewView):
    status_code = 404
    template_name = "404.html"


class Http500PreviewView(HttpErrorPreviewView):
    status_code = 500
    template_name = "500.html"


def page_not_found(request, exception):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)
