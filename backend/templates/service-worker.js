const ATELIER_URL = "/staff/";
const POD_QC_URL = "/staff/atelier/pod/controle-qualite/";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let eventPublicId = "";
  let eventType = "";
  try {
    const payload = event.data ? event.data.json() : {};
    if (UUID_PATTERN.test(payload.event_public_id || "")) {
      eventPublicId = payload.event_public_id;
    }
    if (payload.event_type === "workshop.pod_order_qc_ready") {
      eventType = payload.event_type;
    }
  } catch {
    eventPublicId = "";
  }

  const podReady = eventType === "workshop.pod_order_qc_ready";
  const url = podReady ? POD_QC_URL : ATELIER_URL;
  const tag = eventPublicId ? `atelier-order-${eventPublicId}` : "atelier-new-order";
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(podReady ? "Production POD terminée" : "Nouvelle commande Atelier", {
        body: podReady ? "Toutes les pièces POD ont passé le contrôle qualité." : "Une nouvelle commande est disponible.",
        tag,
        data: { url, eventPublicId },
      }),
      self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
        clients.forEach((client) => {
          client.postMessage({ type: "atelier-notification", eventPublicId, eventType });
        });
      }),
    ])
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const destination = event.notification.data?.url === POD_QC_URL ? POD_QC_URL : ATELIER_URL;
  const target = new URL(destination, self.location.origin);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (clients) => {
      const existing = clients.find((client) => new URL(client.url).origin === self.location.origin);
      if (existing) {
        if ("navigate" in existing) {
          await existing.navigate(target.href);
        }
        return existing.focus();
      }
      return self.clients.openWindow(target.href);
    })
  );
});
