import json

from django.http import HttpResponse


def with_toast(response: HttpResponse, message: str, variant: str = "success") -> HttpResponse:
    response["X-Prenium-Toast"] = json.dumps(
        {"message": message, "variant": variant},
        # Un en-tête HTTP doit rester ASCII. JSON.parse restitue ensuite les accents côté client.
        ensure_ascii=True,
    )
    return response
