from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditlog.services import record_event
from apps.notifications.models import EmailTemplate
from apps.orders.models import Order

TOKEN_PATTERN = re.compile(r"{{\s*([a-z][a-z0-9_.]*)\s*}}")
UNSAFE_TEMPLATE_MARKERS = ("{%", "%}", "{#", "#}")


@dataclass(frozen=True)
class EmailTag:
    key: str
    label: str
    example: str

    @property
    def token(self) -> str:
        return "{{ " + self.key + " }}"


@dataclass(frozen=True)
class EmailTemplateDefinition:
    event: str
    audience: str
    event_label: str
    audience_label: str
    description: str
    default_subject: str
    default_body: str


@dataclass(frozen=True)
class EffectiveEmailTemplate:
    definition: EmailTemplateDefinition
    subject_template: str
    body_template: str
    is_active: bool
    is_customized: bool
    version: int
    updated_at: object | None
    updated_by_email: str

    @property
    def event(self) -> str:
        return self.definition.event

    @property
    def audience(self) -> str:
        return self.definition.audience


EMAIL_TAGS = (
    EmailTag("site.name", "Nom de la marque", "Prenium DTF"),
    EmailTag("customer.name", "Nom du client", "Atelier Démo"),
    EmailTag("customer.billing_email", "E-mail de facturation", "compta@atelier-demo.fr"),
    EmailTag("order.reference", "Référence courte", "a1b2c3d4e5f6"),
    EmailTag(
        "order.public_id",
        "Identifiant public complet",
        "7a16d36c-74b2-4a23-914e-a1b2c3d4e5f6",
    ),
    EmailTag("order.total_amount", "Montant total", "125,50"),
    EmailTag("order.currency", "Devise", "EUR"),
    EmailTag("order.status", "Statut commande", "Soumise"),
    EmailTag("order.billing_mode", "Mode de facturation", "Facturation différée"),
    EmailTag(
        "order.credit_status_message",
        "Message d’encours",
        "Votre encours approche du plafond configuré.",
    ),
    EmailTag("shipment.tracking_number", "Numéro de suivi", "TRK-123456"),
    EmailTag(
        "shipment.tracking_url",
        "Lien de suivi",
        "https://tracking.example.test/TRK-123456",
    ),
    EmailTag("shipment.status", "Statut transporteur", "Colis en route"),
    EmailTag("upload.filename", "Nom du fichier", "visuel-logo-final.png"),
    EmailTag("review.reason", "Motif de correction", "Résolution insuffisante"),
    EmailTag(
        "review.comment",
        "Commentaire Atelier",
        "Merci de fournir une version 300 DPI sur fond transparent.",
    ),
    EmailTag("prospect.first_name", "Prénom du prospect", "Camille"),
    EmailTag("prospect.last_name", "Nom du prospect", "Martin"),
    EmailTag("prospect.company", "Société du prospect", "Atelier Démo"),
    EmailTag("prospect.email", "E-mail du prospect", "camille@atelier-demo.fr"),
    EmailTag("prospect.country", "Pays du prospect", "FR"),
    EmailTag("prospect.siren", "SIREN", "123456789"),
    EmailTag("prospect.vat_number", "N° TVA / fiscal", "BE0123456789"),
    EmailTag("invitation.role", "Rôle invité", "Collaborateur"),
    EmailTag("action.url", "Lien d'action sécurisé", "https://example.test/activation/"),
)
ALLOWED_TAG_KEYS = frozenset(tag.key for tag in EMAIL_TAGS)


def _definition(
    event: str,
    audience: str,
    *,
    event_label: str,
    audience_label: str,
    description: str,
    subject: str,
    body: str,
) -> EmailTemplateDefinition:
    return EmailTemplateDefinition(
        event=event,
        audience=audience,
        event_label=event_label,
        audience_label=audience_label,
        description=description,
        default_subject=subject,
        default_body=body,
    )


EMAIL_TEMPLATE_DEFINITIONS = (
    _definition(
        EmailTemplate.Event.ACCESS_REQUEST_EMAIL_VERIFICATION,
        EmailTemplate.Audience.CLIENT,
        event_label="Vérification demande d'accès",
        audience_label="Prospect",
        description="Confirme que l'adresse professionnelle appartient au demandeur.",
        subject="Confirmez votre demande d'accès Prenium DTF",
        body=(
            "Bonjour {{ prospect.first_name }},\n\n"
            "Merci pour votre demande d'accès au nom de {{ prospect.company }}.\n"
            "Confirmez votre adresse professionnelle avec ce lien valable 48 heures :\n"
            "{{ action.url }}\n\n"
            "Après confirmation, l'équipe IDS examinera votre demande.\n\n"
            "Cordialement,\nL'équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ACCESS_REQUEST_SUBMITTED_INTERNAL,
        EmailTemplate.Audience.INTERNAL,
        event_label="Nouvelle demande d'accès",
        audience_label="Équipe interne",
        description="Alerte IDS après vérification de l'e-mail du prospect.",
        subject="[Accès] Nouvelle demande — {{ prospect.company }}",
        body=(
            "Une demande d'accès vérifiée attend votre décision.\n\n"
            "Société : {{ prospect.company }}\n"
            "Contact : {{ prospect.first_name }} {{ prospect.last_name }}\n"
            "E-mail : {{ prospect.email }}\n"
            "Pays : {{ prospect.country }}\n"
            "SIREN : {{ prospect.siren }}\n"
            "TVA / identifiant fiscal : {{ prospect.vat_number }}\n\n"
            "Examiner la demande : {{ action.url }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ACCESS_REQUEST_APPROVED,
        EmailTemplate.Audience.CLIENT,
        event_label="Demande d'accès validée",
        audience_label="Prospect",
        description="Invite le propriétaire à activer son organisation.",
        subject="Votre accès Prenium DTF est validé",
        body=(
            "Bonjour {{ prospect.first_name }},\n\n"
            "Votre demande pour {{ customer.name }} a été validée.\n"
            "Activez votre compte propriétaire avec ce lien valable 72 heures :\n"
            "{{ action.url }}\n\n"
            "Cordialement,\nL'équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ACCESS_REQUEST_REJECTED,
        EmailTemplate.Audience.CLIENT,
        event_label="Demande d'accès refusée",
        audience_label="Prospect",
        description="Informe le prospect de la décision IDS.",
        subject="Mise à jour de votre demande d'accès Prenium DTF",
        body=(
            "Bonjour {{ prospect.first_name }},\n\n"
            "Nous ne pouvons pas valider votre demande pour {{ prospect.company }} en l'état.\n\n"
            "Motif : {{ review.reason }}\n\n"
            "Vous pouvez répondre à cet e-mail si vous souhaitez apporter des précisions.\n\n"
            "Cordialement,\nL'équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ACCOUNT_ACTIVATED,
        EmailTemplate.Audience.CLIENT,
        event_label="Compte activé",
        audience_label="Client",
        description="Confirmation après activation d'un accès organisationnel.",
        subject="Bienvenue dans l'espace {{ customer.name }}",
        body=(
            "Bonjour,\n\n"
            "Votre accès à l'organisation {{ customer.name }} est maintenant actif "
            "avec le rôle {{ invitation.role }}.\n\n"
            "Connexion : {{ action.url }}\n\n"
            "Cordialement,\nL'équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.CUSTOMER_MEMBER_INVITED,
        EmailTemplate.Audience.CLIENT,
        event_label="Collaborateur invité",
        audience_label="Client",
        description="Invitation sécurisée à rejoindre une organisation.",
        subject="Invitation à rejoindre {{ customer.name }}",
        body=(
            "Bonjour,\n\n"
            "Vous êtes invité à rejoindre {{ customer.name }} sur Prenium DTF "
            "avec le rôle {{ invitation.role }}.\n\n"
            "Accepter l'invitation sous 72 heures : {{ action.url }}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n\n"
            "Cordialement,\nL'équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_CREATED,
        EmailTemplate.Audience.CLIENT,
        event_label="Commande créée",
        audience_label="Client",
        description="Confirmation envoyée après l’enregistrement d’une commande.",
        subject="Commande reçue — {{ customer.name }}",
        body=(
            "Bonjour,\n\n"
            "Nous avons bien enregistré votre commande pour {{ customer.name }}.\n\n"
            "Référence commande : {{ order.reference }}\n"
            "Montant TTC indiqué : {{ order.total_amount }} {{ order.currency }}\n\n"
            "Vous pouvez suivre l’avancement dans votre espace client.\n\n"
            "Cordialement,\nL’équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_CREATED,
        EmailTemplate.Audience.INTERNAL,
        event_label="Commande créée",
        audience_label="Équipe interne",
        description="Alerte interne à la création d’une commande.",
        subject="[Atelier] Nouvelle commande — {{ customer.name }}",
        body=(
            "Une nouvelle commande a été enregistrée.\n\n"
            "Client : {{ customer.name }}\n"
            "Référence : {{ order.reference }}\n"
            "Montant : {{ order.total_amount }} {{ order.currency }}\n"
            "Facturation : {{ order.billing_mode }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.PAYMENT_CAPTURED,
        EmailTemplate.Audience.CLIENT,
        event_label="Paiement confirmé",
        audience_label="Client",
        description="Confirmation envoyée après validation du paiement.",
        subject="Paiement confirmé — commande {{ order.reference }}",
        body=(
            "Bonjour,\n\n"
            "Votre paiement pour la commande {{ order.reference }} "
            "({{ customer.name }}) a bien été enregistré.\n\n"
            "Votre facture est disponible dans votre espace client.\n\n"
            "Cordialement,\nL’équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.PAYMENT_CAPTURED,
        EmailTemplate.Audience.INTERNAL,
        event_label="Paiement confirmé",
        audience_label="Équipe interne",
        description="Alerte interne après confirmation d’un paiement.",
        subject="[Comptabilité] Paiement reçu — {{ order.reference }}",
        body=(
            "Le paiement d’une commande a été confirmé.\n\n"
            "Client : {{ customer.name }}\n"
            "Référence : {{ order.reference }}\n"
            "Montant : {{ order.total_amount }} {{ order.currency }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_PROCESSING,
        EmailTemplate.Audience.CLIENT,
        event_label="Commande en traitement",
        audience_label="Client",
        description="Information envoyée lors de la première prise en charge par l’Atelier.",
        subject="Votre commande est en traitement — {{ order.reference }}",
        body=(
            "Bonjour,\n\n"
            "L’Atelier a pris en charge votre commande {{ order.reference }} "
            "pour {{ customer.name }}.\n\n"
            "Sa préparation est en cours. Vous pouvez suivre son avancement "
            "dans votre espace client.\n\n"
            "Cordialement,\nL’équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_PROCESSING,
        EmailTemplate.Audience.INTERNAL,
        event_label="Commande en traitement",
        audience_label="Équipe interne",
        description="Alerte interne lors du démarrage effectif de la production.",
        subject="[Atelier] Production démarrée — {{ order.reference }}",
        body=(
            "La production d’une commande vient de démarrer.\n\n"
            "Client : {{ customer.name }}\n"
            "Référence : {{ order.reference }}\n"
            "Étape : En traitement"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_READY_TO_SHIP,
        EmailTemplate.Audience.CLIENT,
        event_label="Commande traitée",
        audience_label="Client",
        description="Information envoyée lorsque la production est terminée et prête au départ.",
        subject="Votre commande est prête à être expédiée — {{ order.reference }}",
        body=(
            "Bonjour,\n\n"
            "Votre commande {{ order.reference }} pour {{ customer.name }} a été traitée "
            "par l’Atelier et attend maintenant sa prise en charge par le transporteur.\n\n"
            "Cordialement,\nL’équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_READY_TO_SHIP,
        EmailTemplate.Audience.INTERNAL,
        event_label="Commande traitée",
        audience_label="Équipe interne",
        description="Alerte interne lorsqu’une commande est prête pour l’expédition.",
        subject="[Atelier] Commande prête à expédier — {{ order.reference }}",
        body=(
            "Une commande est prête à être expédiée.\n\n"
            "Client : {{ customer.name }}\n"
            "Référence : {{ order.reference }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_SHIPPED,
        EmailTemplate.Audience.CLIENT,
        event_label="Commande expédiée",
        audience_label="Client",
        description="Information envoyée après le premier scan de prise en charge transporteur.",
        subject="Votre commande a été expédiée — {{ order.reference }}",
        body=(
            "Bonjour,\n\n"
            "Votre commande {{ order.reference }} pour {{ customer.name }} a été prise en "
            "charge par le transporteur.\n\n"
            "Numéro de suivi : {{ shipment.tracking_number }}\n"
            "Suivre mon colis : {{ shipment.tracking_url }}\n\n"
            "Cordialement,\nL’équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_SHIPPED,
        EmailTemplate.Audience.INTERNAL,
        event_label="Commande expédiée",
        audience_label="Équipe interne",
        description="Alerte interne après la première prise en charge transporteur.",
        subject="[Expédition] Commande expédiée — {{ order.reference }}",
        body=(
            "Une commande a été prise en charge par le transporteur.\n\n"
            "Client : {{ customer.name }}\n"
            "Référence : {{ order.reference }}\n"
            "Suivi : {{ shipment.tracking_number }}\n"
            "Statut : {{ shipment.status }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_PRICED,
        EmailTemplate.Audience.CLIENT,
        event_label="Commande tarifée",
        audience_label="Client",
        description="Information envoyée après calcul du tarif B2B.",
        subject="Votre commande est tarifée — {{ customer.name }}",
        body=(
            "Bonjour,\n\n"
            "Le montant de votre commande {{ order.reference }} ({{ customer.name }}) "
            "a été calculé après contrôle technique.\n\n"
            "Total TTC : {{ order.total_amount }} {{ order.currency }}\n"
            "{{ order.credit_status_message }}\n\n"
            "Retrouvez le détail dans votre espace client.\n\n"
            "Cordialement,\nL’équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.ORDER_PRICED,
        EmailTemplate.Audience.INTERNAL,
        event_label="Commande tarifée",
        audience_label="Équipe interne",
        description="Alerte interne après calcul du tarif B2B.",
        subject="[Commercial] Commande tarifée — {{ order.reference }}",
        body=(
            "Le tarif d’une commande B2B a été calculé.\n\n"
            "Client : {{ customer.name }}\n"
            "Référence : {{ order.reference }}\n"
            "Total TTC : {{ order.total_amount }} {{ order.currency }}\n"
            "{{ order.credit_status_message }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.FILE_CORRECTION_REQUESTED,
        EmailTemplate.Audience.CLIENT,
        event_label="Correction fichier demandée",
        audience_label="Client",
        description="Message envoyé lorsqu’un fichier doit être remplacé avant production.",
        subject="Action requise — fichier {{ upload.filename }}",
        body=(
            "Bonjour,\n\n"
            "L’Atelier a contrôlé le fichier {{ upload.filename }} de la commande "
            "{{ order.reference }}.\n\n"
            "Correction demandée : {{ review.reason }}\n"
            "Précision Atelier : {{ review.comment }}\n\n"
            "Merci de transmettre une version corrigée depuis votre espace client.\n\n"
            "Cordialement,\nL’équipe {{ site.name }}"
        ),
    ),
    _definition(
        EmailTemplate.Event.FILE_CORRECTION_REQUESTED,
        EmailTemplate.Audience.INTERNAL,
        event_label="Correction fichier demandée",
        audience_label="Équipe interne",
        description="Copie interne d’une demande de correction envoyée au client.",
        subject="[Atelier] Correction demandée — {{ order.reference }}",
        body=(
            "Une correction fichier a été demandée.\n\n"
            "Client : {{ customer.name }}\n"
            "Commande : {{ order.reference }}\n"
            "Fichier : {{ upload.filename }}\n"
            "Motif : {{ review.reason }}\n"
            "Commentaire : {{ review.comment }}"
        ),
    ),
)
DEFINITIONS_BY_KEY = {
    (definition.event, definition.audience): definition for definition in EMAIL_TEMPLATE_DEFINITIONS
}


def get_template_definition(event: str, audience: str) -> EmailTemplateDefinition:
    try:
        return DEFINITIONS_BY_KEY[(event, audience)]
    except KeyError as exc:
        raise ValidationError("Modèle d’e-mail inconnu.") from exc


def _validate_template_text(value: str, *, field_label: str) -> None:
    if any(marker in value for marker in UNSAFE_TEMPLATE_MARKERS):
        raise ValidationError(
            f"{field_label} contient une instruction interdite. "
            "Utilisez uniquement les tags proposés."
        )

    tokens = TOKEN_PATTERN.findall(value)
    unknown_tokens = sorted(set(tokens) - ALLOWED_TAG_KEYS)
    if unknown_tokens:
        unknown = ", ".join("{{ " + token + " }}" for token in unknown_tokens)
        raise ValidationError(f"Tag inconnu dans {field_label.lower()} : {unknown}.")

    remainder = TOKEN_PATTERN.sub("", value)
    if "{{" in remainder or "}}" in remainder:
        raise ValidationError(
            f"{field_label} contient un tag mal formé. Utilisez la forme {{{{ nom.du.tag }}}}."
        )


def validate_template_pair(*, subject_template: str, body_template: str) -> None:
    if "\n" in subject_template or "\r" in subject_template:
        raise ValidationError("L’objet de l’e-mail doit tenir sur une seule ligne.")
    if not subject_template.strip():
        raise ValidationError("L’objet de l’e-mail est obligatoire.")
    if not body_template.strip():
        raise ValidationError("Le message de l’e-mail est obligatoire.")
    _validate_template_text(subject_template, field_label="L’objet")
    _validate_template_text(body_template, field_label="Le message")


def render_template_text(template: str, context: dict[str, str]) -> str:
    _validate_template_text(template, field_label="Le modèle")

    def replace(match: re.Match) -> str:
        return context.get(match.group(1), "")

    return TOKEN_PATTERN.sub(replace, template)


def _format_amount(amount: Decimal | str) -> str:
    return f"{Decimal(str(amount)):.2f}".replace(".", ",")


def _credit_status_message(order: Order) -> str:
    if order.credit_hold_status == Order.CreditHoldStatus.BLOCKED:
        return (
            "Attention : votre encours dépasse le plafond configuré. "
            "Merci de contacter le service commercial."
        )
    if order.credit_hold_status == Order.CreditHoldStatus.WARNING:
        return "Note : votre encours approche ou dépasse le plafond configuré."
    return ""


def context_for_order(order: Order) -> dict[str, str]:
    return {
        "site.name": "Prenium DTF",
        "customer.name": order.customer.name,
        "customer.billing_email": order.customer.billing_email or "",
        "order.reference": order.short_ref,
        "order.public_id": str(order.public_id),
        "order.total_amount": _format_amount(order.total_amount),
        "order.currency": order.currency,
        "order.status": order.get_status_display(),
        "order.billing_mode": order.get_billing_mode_display(),
        "order.credit_status_message": _credit_status_message(order),
    }


def sample_context() -> dict[str, str]:
    return {tag.key: tag.example for tag in EMAIL_TAGS}


class EmailTemplateService:
    def get_effective_template(self, *, event: str, audience: str) -> EffectiveEmailTemplate:
        definition = get_template_definition(event, audience)
        override = (
            EmailTemplate.objects.filter(event=event, audience=audience)
            .select_related("updated_by")
            .first()
        )
        if override is None:
            return EffectiveEmailTemplate(
                definition=definition,
                subject_template=definition.default_subject,
                body_template=definition.default_body,
                is_active=True,
                is_customized=False,
                version=0,
                updated_at=None,
                updated_by_email="",
            )
        return EffectiveEmailTemplate(
            definition=definition,
            subject_template=override.subject_template,
            body_template=override.body_template,
            is_active=override.is_active,
            is_customized=True,
            version=override.version,
            updated_at=override.updated_at,
            updated_by_email=getattr(override.updated_by, "email", "") or "",
        )

    def list_effective_templates(self) -> list[EffectiveEmailTemplate]:
        overrides = {
            (template.event, template.audience): template
            for template in EmailTemplate.objects.select_related("updated_by").all()
        }
        rows = []
        for definition in EMAIL_TEMPLATE_DEFINITIONS:
            override = overrides.get((definition.event, definition.audience))
            if override is None:
                rows.append(
                    EffectiveEmailTemplate(
                        definition=definition,
                        subject_template=definition.default_subject,
                        body_template=definition.default_body,
                        is_active=True,
                        is_customized=False,
                        version=0,
                        updated_at=None,
                        updated_by_email="",
                    )
                )
                continue
            rows.append(
                EffectiveEmailTemplate(
                    definition=definition,
                    subject_template=override.subject_template,
                    body_template=override.body_template,
                    is_active=override.is_active,
                    is_customized=True,
                    version=override.version,
                    updated_at=override.updated_at,
                    updated_by_email=getattr(override.updated_by, "email", "") or "",
                )
            )
        return rows

    def render_for_order(
        self,
        *,
        event: str,
        audience: str,
        order: Order,
        context_overrides: dict[str, str] | None = None,
    ) -> tuple[str, str] | None:
        context = context_for_order(order)
        if context_overrides:
            context.update({key: str(value) for key, value in context_overrides.items()})
        return self.render_for_context(event=event, audience=audience, context=context)

    def render_for_context(
        self,
        *,
        event: str,
        audience: str,
        context: dict[str, str],
    ) -> tuple[str, str] | None:
        template = self.get_effective_template(event=event, audience=audience)
        if not template.is_active:
            return None
        # Les exemples servent uniquement à l'aperçu du backoffice. Un e-mail réel
        # ne doit jamais compléter une donnée absente avec une valeur fictive.
        merged_context = {key: str(value) for key, value in context.items()}
        subject = render_template_text(template.subject_template, merged_context)
        subject = re.sub(r"[\r\n]+", " ", subject).strip()
        return subject, render_template_text(template.body_template, merged_context)

    @transaction.atomic
    def save_override(
        self,
        *,
        event: str,
        audience: str,
        subject_template: str,
        body_template: str,
        is_active: bool,
        actor,
        ip_address: str | None = None,
    ) -> EmailTemplate:
        get_template_definition(event, audience)
        validate_template_pair(
            subject_template=subject_template,
            body_template=body_template,
        )
        template = (
            EmailTemplate.objects.select_for_update().filter(event=event, audience=audience).first()
        )
        if template is None:
            template = EmailTemplate(event=event, audience=audience)
        else:
            template.version += 1
        template.subject_template = subject_template
        template.body_template = body_template
        template.is_active = is_active
        template.updated_by = actor
        template.full_clean()
        template.save()
        record_event(
            action="notifications.email_template.updated",
            actor=actor,
            target=template,
            ip_address=ip_address,
            metadata={
                "event": event,
                "audience": audience,
                "version": template.version,
                "is_active": is_active,
            },
        )
        return template
