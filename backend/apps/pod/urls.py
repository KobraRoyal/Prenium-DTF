from django.urls import path

from apps.pod.views_webhooks import ShopifyPodFulfillmentWebhookView

app_name = "pod"

urlpatterns = [
    path(
        "webhooks/shopify/pod/fulfillment/",
        ShopifyPodFulfillmentWebhookView.as_view(),
        name="shopify-fulfillment-webhook",
    ),
]
