from django.urls import path

from apps.pod.views_oauth import ShopifyPodOAuthCallbackView
from apps.pod.views_webhooks import ShopifyPodFulfillmentWebhookView

app_name = "pod"

urlpatterns = [
    path(
        "webhooks/shopify/pod/fulfillment/",
        ShopifyPodFulfillmentWebhookView.as_view(),
        name="shopify-fulfillment-webhook",
    ),
    path(
        "integrations/shopify/pod/oauth/callback/",
        ShopifyPodOAuthCallbackView.as_view(),
        name="shopify-oauth-callback",
    ),
]
