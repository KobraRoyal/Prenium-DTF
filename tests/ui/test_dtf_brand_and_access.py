from html.parser import HTMLParser

import pytest
from django.test import Client
from django.urls import reverse


class AccessLinks(HTMLParser):
    """Read actual public entrypoint labels, including nested SVG/button copy."""

    def __init__(self, target):
        super().__init__()
        self.target = target
        self.collecting = False
        self.labels = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.collecting = dict(attrs).get("href") == self.target
            self.parts = []

    def handle_data(self, data):
        if self.collecting:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.collecting:
            self.labels.append(" ".join(" ".join(self.parts).split()))
            self.collecting = False


@pytest.mark.django_db
@pytest.mark.parametrize("route", ["home", "services", "portal:login", "prospects:step1"])
def test_public_journey_uses_one_brand_and_an_honest_b2b_entrypoint(route):
    response = Client().get(reverse(route))
    assert response.status_code == 200
    html = response.content.decode()
    assert '<span class="ui-brand-lockup__name">Prenium DTF</span>' in html
    assert '<span class="ui-brand-lockup__subtitle">By IDS.Supply</span>' in html
    assert 'class="dtf-logo"' not in html
    assert "via IDS supply" not in html
    if route != "prospects:step1":
        links = AccessLinks(reverse("prospects:step1"))
        links.feed(html)
        expected = "Demander mon accès pro" if route == "home" else "Demander votre accès"
        assert expected in links.labels
    if route in {"home", "portal:login"}:
        assert "exclusivement réservé aux professionnels (B2B)" in html
    if route == "home":
        links = AccessLinks(reverse("prospects:step1"))
        links.feed(html)
        assert all(label == "Demander mon accès pro" for label in links.labels)
        assert "6 € HT" in html
        assert "Lecture du bas vers le haut avant pose" not in html
        positions = [html.index(f'id="layer-tab-{index}"') for index in range(4)]
        assert positions == sorted(positions)
