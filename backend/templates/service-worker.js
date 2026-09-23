const ATELIER_URL = "/staff/";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let eventPublicId = "";
  try {
    const payload = event.data ? event.data.json() : {};
    if (UUID_PATTERN.test(payload.event_public_id || "")) {
      eventPublicId = payload.event_public_id;
    }
  } catch {
    eventPublicId = "";
  }

  const tag = eventPublicId ? `atelier-order-${eventPublicId}` : "atelier-new-order";
  event.waitUntil(
    Promise.all([
      self.registration.showNotification("Nouvelle commande Atelier", {
        body: "Une nouvelle commande est disponible.",
        tag,
        data: { url: ATELIER_URL, eventPublicId },
      }),
      self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
        clients.forEach((client) => {
          client.postMessage({ type: "atelier-notification", eventPublicId });
        });
      }),
    ])
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(ATELIER_URL, self.location.origin);
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
