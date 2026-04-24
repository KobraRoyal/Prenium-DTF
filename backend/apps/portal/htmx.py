import json

from django.http import HttpResponse


def with_toast(response: HttpResponse, message: str, variant: str = "success") -> HttpResponse:
    response["X-Prenium-Toast"] = json.dumps(
        {"message": message, "variant": variant},
        ensure_ascii=False,
    )
    return response
