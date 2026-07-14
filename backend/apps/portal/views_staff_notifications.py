from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.notifications.forms import EmailTemplateForm
from apps.notifications.models import EmailTemplate
from apps.notifications.services.email_templates import (
    EMAIL_TAGS,
    EmailTemplateService,
    get_template_definition,
    render_template_text,
    sample_context,
)
from apps.portal.views_common import StaffDomainPermissionMixin

email_template_service = EmailTemplateService()


def _client_ip(request) -> str | None:
    value = (request.META.get("REMOTE_ADDR") or "").strip()
    return value or None


class StaffEmailTemplateListView(StaffDomainPermissionMixin, View):
    required_permission = "notifications.view_emailtemplate"
    template_name = "portal/staff/email_templates/list.html"

    def get(self, request):
        templates = email_template_service.list_effective_templates()
        return render(
            request,
            self.template_name,
            {
                "client_templates": [
                    row
                    for row in templates
                    if row.audience == EmailTemplate.Audience.CLIENT
                ],
                "internal_templates": [
                    row
                    for row in templates
                    if row.audience == EmailTemplate.Audience.INTERNAL
                ],
                "internal_recipient_count": len(
                    getattr(settings, "INTERNAL_NOTIFICATION_EMAILS", [])
                ),
                "can_edit_email_templates": request.user.has_perm(
                    "notifications.change_emailtemplate"
                ),
                "nav_mode": "staff",
                "nav_key": "staff-email-templates",
            },
        )


class StaffEmailTemplateEditView(StaffDomainPermissionMixin, View):
    required_permission = "notifications.view_emailtemplate"
    template_name = "portal/staff/email_templates/edit.html"

    def _definition(self, event: str, audience: str):
        try:
            return get_template_definition(event, audience)
        except ValidationError as exc:
            raise Http404 from exc

    def _render(
        self,
        request,
        *,
        event: str,
        audience: str,
        form: EmailTemplateForm,
        preview_subject: str,
        preview_body: str,
        saved: bool = False,
    ):
        definition = self._definition(event, audience)
        effective = email_template_service.get_effective_template(
            event=event,
            audience=audience,
        )
        return render(
            request,
            self.template_name,
            {
                "definition": definition,
                "effective_template": effective,
                "form": form,
                "email_tags": EMAIL_TAGS,
                "preview_subject": preview_subject,
                "preview_body": preview_body,
                "saved": saved,
                "can_edit_email_templates": request.user.has_perm(
                    "notifications.change_emailtemplate"
                ),
                "nav_mode": "staff",
                "nav_key": "staff-email-templates",
            },
        )

    def get(self, request, event: str, audience: str):
        self._definition(event, audience)
        effective = email_template_service.get_effective_template(
            event=event,
            audience=audience,
        )
        form = EmailTemplateForm(
            initial={
                "subject_template": effective.subject_template,
                "body_template": effective.body_template,
                "is_active": effective.is_active,
            }
        )
        context = sample_context()
        return self._render(
            request,
            event=event,
            audience=audience,
            form=form,
            preview_subject=render_template_text(effective.subject_template, context),
            preview_body=render_template_text(effective.body_template, context),
            saved=request.GET.get("saved") == "1",
        )

    def post(self, request, event: str, audience: str):
        if not request.user.has_perm("notifications.change_emailtemplate"):
            raise PermissionDenied
        self._definition(event, audience)
        form = EmailTemplateForm(request.POST)
        preview_subject = ""
        preview_body = ""
        if form.is_valid():
            context = sample_context()
            preview_subject = render_template_text(
                form.cleaned_data["subject_template"], context
            )
            preview_body = render_template_text(form.cleaned_data["body_template"], context)
            if request.POST.get("action") == "preview":
                return self._render(
                    request,
                    event=event,
                    audience=audience,
                    form=form,
                    preview_subject=preview_subject,
                    preview_body=preview_body,
                )
            email_template_service.save_override(
                event=event,
                audience=audience,
                subject_template=form.cleaned_data["subject_template"],
                body_template=form.cleaned_data["body_template"],
                is_active=form.cleaned_data["is_active"],
                actor=request.user,
                ip_address=_client_ip(request),
            )
            url = reverse(
                "portal:staff-email-template-edit",
                kwargs={"event": event, "audience": audience},
            )
            return HttpResponseRedirect(f"{url}?saved=1")
        return self._render(
            request,
            event=event,
            audience=audience,
            form=form,
            preview_subject=preview_subject,
            preview_body=preview_body,
        )
