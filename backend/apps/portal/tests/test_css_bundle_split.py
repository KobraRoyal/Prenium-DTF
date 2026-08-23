from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC_CSS = Path(settings.BASE_DIR) / "static_src" / "css"
ENTRIES = STATIC_CSS / "entries"
TEMPLATES = Path(settings.BASE_DIR) / "templates"

CLIENT_SURFACE_MAX_BYTES = 400_000
STAFF_SURFACE_MAX_BYTES = 420_000
PROSPECT_SURFACE_MAX_BYTES = 380_000


def file_size(path: Path) -> int:
    if not path.exists():
        return 0
    return path.stat().st_size


class CssBundleSplitTests(SimpleTestCase):
    def test_entry_files_exist_for_lot4_split(self) -> None:
        for name in [
            "portal-core.css",
            "portal-client.css",
            "portal-staff.css",
            "prospect.css",
        ]:
            with self.subTest(entry=name):
                self.assertTrue((ENTRIES / name).exists(), f"Missing entries/{name}")

    def test_surface_styles_partial_loads_role_bundles(self) -> None:
        partial = (TEMPLATES / "components/portal/surface_styles.html").read_text(encoding="utf-8")
        layout = (TEMPLATES / "portal/layout.html").read_text(encoding="utf-8")
        tunnel = (TEMPLATES / "prospects/base_tunnel.html").read_text(encoding="utf-8")

        self.assertIn("portal-core.css", partial)
        self.assertIn("portal-client.css", partial)
        self.assertIn("portal-staff.css", partial)
        self.assertIn("prospect.css", partial)
        self.assertIn("surface_styles.html", layout)
        self.assertIn('portal_surface="prospect"', tunnel)
        self.assertNotIn("portal.css", layout)

    def test_split_bundles_are_smaller_than_monolith_for_client_and_staff(self) -> None:
        monolith = file_size(STATIC_CSS / "portal.css")
        core = file_size(STATIC_CSS / "portal-core.css")
        client = file_size(STATIC_CSS / "portal-client.css")
        staff = file_size(STATIC_CSS / "portal-staff.css")
        prospect = file_size(STATIC_CSS / "prospect.css")

        self.assertGreater(monolith, 0, "Run npm run build:css to generate portal.css baseline")
        self.assertGreater(core, 0)
        self.assertGreater(client, 0)
        self.assertGreater(staff, 0)
        self.assertGreater(prospect, 0)

        client_surface = core + client
        staff_surface = core + staff
        prospect_surface = core + prospect

        self.assertLess(client_surface, monolith)
        self.assertLess(staff_surface, monolith)
        self.assertLess(prospect_surface, monolith)
        self.assertLess(client_surface, CLIENT_SURFACE_MAX_BYTES)
        self.assertLess(staff_surface, STAFF_SURFACE_MAX_BYTES)
        self.assertLess(prospect_surface, PROSPECT_SURFACE_MAX_BYTES)

        client_entry = (ENTRIES / "portal-client.css").read_text(encoding="utf-8")
        staff_entry = (ENTRIES / "portal-staff.css").read_text(encoding="utf-8")
        self.assertNotIn("inspection-workbench", client_entry)
        self.assertNotIn("access-request-queue", client_entry)
        self.assertNotIn("client-dashboard.css", staff_entry)
        self.assertNotIn("gang-sheet.css", staff_entry)
