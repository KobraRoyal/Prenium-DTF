"""Validation des liens fournis pour les fichiers externes."""

import ipaddress
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def validate_external_url(value: str) -> str:
    """Accept only a public HTTP(S) URL; never resolve or fetch the host."""
    cleaned = str(value or "").strip()
    if not cleaned or len(cleaned) > 2000:
        raise ValidationError("Indiquez un lien de téléchargement valide (2 000 caractères max).")
    try:
        parsed = urlsplit(cleaned)
        host = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port  # Raises ValueError for malformed ports.
    except ValueError as exc:
        raise ValidationError("Le lien de téléchargement est invalide.") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise ValidationError("Le lien doit commencer par http:// ou https://.")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("Le lien ne peut pas contenir d'identifiants de connexion.")
    if port is not None and not 1 <= port <= 65535:
        raise ValidationError("Le port du lien est invalide.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test")):
        raise ValidationError("Le lien doit désigner un hôte public.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.startswith(".") or host.endswith("."):
            raise ValidationError("Le lien doit désigner un hôte public.") from None
    else:
        if not address.is_global:
            raise ValidationError("Le lien doit désigner une adresse publique.")
    try:
        URLValidator(schemes=["http", "https"])(cleaned)
    except ValidationError as exc:
        raise ValidationError("Le lien de téléchargement est invalide.") from exc
    return cleaned


def normalize_external_visual_count(value) -> int:
    text = str(value).strip()
    if not text.isascii() or not text.isdecimal() or len(text) > 5:
        raise ValidationError("Indiquez un nombre entier de visuels entre 1 et 10 000.")
    count = int(text)
    if not 1 <= count <= 10000:
        raise ValidationError("Indiquez un nombre entier de visuels entre 1 et 10 000.")
    return count
