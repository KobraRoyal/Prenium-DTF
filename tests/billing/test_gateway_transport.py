from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import Request

import pytest
from apps.billing.services.gateways import PaymentGatewayError, open_provider_request


def test_authenticated_provider_request_does_not_follow_redirect():
    redirected_requests = []

    class DestinationHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            redirected_requests.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            return

    destination = ThreadingHTTPServer(("127.0.0.1", 0), DestinationHandler)

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/receive")
            self.end_headers()

        def log_message(self, *args):
            return

    origin = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    destination_thread = Thread(target=destination.serve_forever, daemon=True)
    origin_thread = Thread(target=origin.serve_forever, daemon=True)
    destination_thread.start()
    origin_thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{origin.server_port}/checkout",
            headers={"Authorization": "Bearer test-secret"},
        )
        with pytest.raises(PaymentGatewayError, match="Redirection"):
            open_provider_request(request, timeout=2)
        assert redirected_requests == []
    finally:
        origin.shutdown()
        destination.shutdown()
        origin.server_close()
        destination.server_close()
        origin_thread.join(timeout=2)
        destination_thread.join(timeout=2)
