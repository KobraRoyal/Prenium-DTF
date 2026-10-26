"""Public legal pages. Values come from settings only; nothing is resolved per customer."""

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class LegalFact:
    label: str
    value: str

    @property
    def missing(self) -> bool:
        return not self.value


@dataclass(frozen=True)
class LegalPage:
    slug: str
    path: str
    url_name: str
    title: str
    template_name: str


LEGAL_PAGES = (
    LegalPage("mentions", "mentions-legales/", "legal_notice", "Mentions légales", "shop/legal/notice.html"),
    LegalPage(
        "conditions",
        "conditions-commerciales/",
        "legal_terms",
        "Conditions commerciales",
        "shop/legal/terms.html",
    ),
    LegalPage(
        "confidentialite",
        "confidentialite/",
        "legal_privacy",
        "Confidentialité",
        "shop/legal/privacy.html",
    ),
)


class LegalIdentityService:
    PUBLISHER_FIELDS = (
        ("company_name", "Raison sociale"),
        ("legal_form", "Forme juridique"),
        ("share_capital", "Capital social"),
        ("head_office", "Siège social"),
        ("registration", "Immatriculation (SIREN / RCS)"),
        ("vat_number", "TVA intracommunautaire"),
        ("publication_director", "Directeur de la publication"),
    )
    CONTACT_FIELDS = (
        ("contact_email", "E-mail"),
        ("contact_phone", "Téléphone"),
    )
    HOST_FIELDS = (
        ("host_name", "Hébergeur"),
        ("host_address", "Adresse de l’hébergeur"),
    )

    def __init__(self, identity: dict | None = None):
        self.identity = identity if identity is not None else settings.LEGAL_IDENTITY

    def _facts(self, fields) -> list[LegalFact]:
        return [LegalFact(label, self.identity.get(key, "")) for key, label in fields]

    def contact_email(self) -> str:
        return self.identity.get("contact_email") or settings.SUPPORT_CONTACT_EMAIL

    def snapshot(self) -> dict:
        contact = self._facts(self.CONTACT_FIELDS)
        if contact[0].missing and settings.SUPPORT_CONTACT_EMAIL:
            contact[0] = LegalFact(contact[0].label, settings.SUPPORT_CONTACT_EMAIL)
        groups = {
            "publisher": self._facts(self.PUBLISHER_FIELDS),
            "contact": contact,
            "host": self._facts(self.HOST_FIELDS),
        }
        return {
            **groups,
            "contact_email": self.contact_email(),
            "is_complete": not any(fact.missing for facts in groups.values() for fact in facts),
        }
