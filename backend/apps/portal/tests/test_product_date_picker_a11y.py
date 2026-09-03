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
        self.assertIn("aria-label=\"{{ label|default:'Choisir une date' }}\"", source)
        self.assertIn("data-picker-mode=\"{{ picker_mode|default:'date' }}\"", source)
        self.assertIn("picker_mode == 'month'", source)
        self.assertIn('class="product-date-picker__trigger-icon"', source)
        self.assertEqual(source.count('class="product-date-picker__trigger-icon"'), 1)
        self.assertNotIn("product-date-picker__trigger-chevron", source)
        self.assertIn('class="product-date-picker__nav-icon"', source)
        self.assertNotIn(">‹<", source)
        self.assertNotIn(">›<", source)

    def test_calendar_runtime_manages_grid_focus_and_keyboard_navigation(self) -> None:
        source = (Path(settings.BASE_DIR) / "static_src/js/product-date-picker.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("function initProductMonthPicker(root)", source)
        self.assertIn("parseISOMonth(hidden.value)", source)
        self.assertIn("MONTHS_SHORT_FR", source)
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
