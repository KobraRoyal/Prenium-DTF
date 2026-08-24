from django.http import HttpRequest
from django.template import Context, Template
from django.test import SimpleTestCase


class UiListTabsTagTests(SimpleTestCase):
    def test_ui_list_tabs_builds_href_with_preserved_query(self) -> None:
        request = HttpRequest()
        request.GET = {"q": "acme"}
        template = Template(
            "{% load ui_tags %}"
            '{% ui_list_tabs tabs aria_label="Filtrer" url_name="portal:staff-access-request-list" '
            'query_param="status" preserve_query="q" %}'
        )
        rendered = template.render(
            Context(
                {
                    "request": request,
                    "tabs": [
                        {
                            "value": "pending_review",
                            "label": "À examiner",
                            "count": 2,
                            "is_active": True,
                        }
                    ],
                    "aria_label": "Filtrer",
                }
            )
        )
        self.assertIn('class="ui-list-tabs"', rendered)
        self.assertIn('class="ui-list-tabs__tab is-active', rendered)
        self.assertIn("status=pending_review", rendered)
        self.assertIn("q=acme", rendered)
        self.assertIn('aria-current="page"', rendered)
        self.assertIn("ui-list-tabs__count", rendered)

    def test_ui_list_tabs_supports_htmx_navigation(self) -> None:
        template = Template(
            "{% load ui_tags %}"
            '{% ui_list_tabs tabs aria_label="Filtrer" url_name="portal:staff-atelier-operations" '
            'query_param="queue" preserve_query="q" htmx_target="#atelier-operations-panel" '
            'htmx_indicator="#portal-htmx-indicator" %}'
        )
        rendered = template.render(
            Context(
                {
                    "request": HttpRequest(),
                    "tabs": [
                        {
                            "key": "active",
                            "label": "À traiter",
                            "count": 4,
                            "is_active": True,
                        }
                    ],
                }
            )
        )
        self.assertIn('hx-target="#atelier-operations-panel"', rendered)
        self.assertIn('hx-indicator="#portal-htmx-indicator"', rendered)
        self.assertIn('hx-push-url="true"', rendered)
        self.assertIn("queue=active", rendered)
