from django import forms

from apps.gang_sheets.models import GangSheetSiteSettings


class GangSheetSiteSettingsForm(forms.ModelForm):
    class Meta:
        model = GangSheetSiteSettings
        fields = (
            "roll_width_mm",
            "item_spacing_mm",
            "minimum_height_mm",
            "maximum_height_mm",
            "height_step_mm",
        )

    def clean(self):
        data = super().clean()
        minimum = data.get("minimum_height_mm")
        maximum = data.get("maximum_height_mm")
        if minimum is not None and maximum is not None and maximum <= minimum:
            self.add_error("maximum_height_mm", "La hauteur maximale doit dépasser le minimum.")
        return data
