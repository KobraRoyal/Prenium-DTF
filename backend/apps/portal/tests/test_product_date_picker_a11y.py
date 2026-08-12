from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ProductDatePickerAccessibilityTests(SimpleTestCase):
    def test_calendar_exposes_labelled_grid_semantics(self) -> None:
        source = (
            Path(settings.BASE_DIR) / "templates/components/forms/product_date_field.html"
        ).read_text(encoding="utf-8")

        self.assertIn('role="dialog"', source)
        self.assertIn('role="grid"', source)
        self.assertIn('aria-labelledby="{{ id }}-month"', source)
        self.assertIn('aria-live="polite"', source)

    def test_calendar_runtime_manages_grid_focus_and_keyboard_navigation(self) -> None:
        source = (Path(settings.BASE_DIR) / "static_src/js/product-date-picker.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('setAttribute("role", "row")', source)
        self.assertIn('setAttribute("role", "gridcell")', source)
        self.assertIn('setAttribute("aria-selected", "true")', source)
        self.assertIn("focusCalendar(focusTarget)", source)
        self.assertIn("close({ restoreFocus: true })", source)
        for key in [
            "ArrowLeft",
            "ArrowRight",
            "ArrowUp",
            "ArrowDown",
            "Home",
            "End",
            "PageUp",
            "PageDown",
            "Escape",
        ]:
            with self.subTest(key=key):
                if key == "Escape":
                    self.assertIn('event.key === "Escape"', source)
                else:
                    self.assertIn(f'case "{key}"', source)
