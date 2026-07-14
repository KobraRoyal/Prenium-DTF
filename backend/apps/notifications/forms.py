from django import forms

from apps.notifications.services.email_templates import validate_template_pair


class EmailTemplateForm(forms.Form):
    subject_template = forms.CharField(max_length=255, strip=False)
    body_template = forms.CharField(strip=False, widget=forms.Textarea)
    is_active = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        subject = cleaned_data.get("subject_template")
        body = cleaned_data.get("body_template")
        if subject is None or body is None:
            return cleaned_data
        validate_template_pair(subject_template=subject, body_template=body)
        return cleaned_data
