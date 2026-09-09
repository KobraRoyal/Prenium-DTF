const POLL_INTERVAL_MS = 20000;
const UUID_PLACEHOLDER = "00000000-0000-0000-0000-000000000000";
const SUBSCRIPTION_STORAGE_KEY = "prenium.atelier.pushSubscriptionId";
const EVENT_STORAGE_KEY = "prenium.atelier.seenPushEvents";
const MAX_SEEN_EVENTS = 100;

function decodeVapidKey(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const binary = window.atob((value + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function csrfToken(root) {
  return root.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
}

async function jsonRequest(root, url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(options.method === "POST" ? { "X-CSRFToken": csrfToken(root) } : {}),
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) {
    return null;
  }
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error?.message || "Les notifications ne sont pas disponibles.");
  }
  return payload;
}

function seenEvents() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(EVENT_STORAGE_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function markEventSeen(publicId) {
  if (!publicId) return false;
  const seen = seenEvents();
  if (seen.has(publicId)) return false;
  seen.add(publicId);
  sessionStorage.setItem(EVENT_STORAGE_KEY, JSON.stringify(Array.from(seen).slice(-MAX_SEEN_EVENTS)));
  return true;
}

function refreshDashboard(root) {
  if (!window.htmx?.ajax) return;
  window.htmx.ajax("GET", root.dataset.dashboardRefreshUrl, {
    target: "#atelier-dashboard-live-region",
    select: "#atelier-dashboard-live-region",
    swap: "outerHTML",
  });
  // La notification est l'événement temps réel de l'Atelier : synchroniser
  // aussi les priorités et compteurs sans redessiner les graphiques Chart.js.
  if (document.getElementById("atelier-production-health")) {
    window.htmx.ajax("GET", root.dataset.dashboardRefreshUrl, {
      target: "#atelier-production-health",
      select: "#atelier-production-health",
      swap: "outerHTML",
    });
  }
}

function announceEvent(root, publicId) {
  if (!markEventSeen(publicId)) return;
  window.preniumToast?.("Une nouvelle commande est disponible dans l’Atelier.", "info");
  refreshDashboard(root);
}

function setControlState(root, state) {
  const status = root.querySelector("[data-push-status]");
  const button = root.querySelector("[data-push-toggle]");
  const help = root.querySelector("[data-push-help]");
  const labels = {
    loading: ["Vérification…", "Vérification…", "Vérification des alertes sur cet appareil."],
    enabled: ["Alertes activées", "Désactiver les alertes", "Les nouvelles commandes peuvent apparaître dans le centre de notifications."],
    disabled: ["Alertes désactivées", "Activer les alertes", "Votre navigateur demandera votre accord uniquement après un clic sur le bouton."],
    denied: ["Alertes refusées", "Alertes refusées", "Autorisez les notifications dans les réglages du navigateur pour les activer."],
    unsupported: ["Alertes non compatibles", "Alertes non compatibles", "Ce navigateur ne prend pas en charge les notifications système."],
    unavailable: ["Alertes indisponibles", "Alertes indisponibles", "Le service de notification n’est pas configuré."],
    error: ["Erreur de vérification", "Réessayer", "La vérification a échoué. Le suivi automatique de la page reste actif."],
  };
  const [statusText, buttonText, helpText] = labels[state];
  status.textContent = statusText;
  button.textContent = buttonText;
  help.textContent = helpText;
  button.disabled = ["loading", "denied", "unsupported", "unavailable"].includes(state);
  button.dataset.action = state === "enabled" ? "disable" : "enable";
  root.dataset.pushState = state;
}

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function registerWorker() {
  await navigator.serviceWorker.register("/service-worker.js", { scope: "/" });
  return navigator.serviceWorker.ready;
}

async function serializeSubscription(subscription) {
  const data = subscription.toJSON();
  return {
    endpoint: data.endpoint,
    p256dh: data.keys?.p256dh || "",
    auth: data.keys?.auth || "",
  };
}

async function reconcileSubscription(root, subscription) {
  const payload = await jsonRequest(root, root.dataset.subscribeUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(await serializeSubscription(subscription)),
  });
  localStorage.setItem(SUBSCRIPTION_STORAGE_KEY, payload.subscription.public_id);
  return payload.subscription.public_id;
}

async function enablePush(root, vapidPublicKey) {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    setControlState(root, permission === "denied" ? "denied" : "disabled");
    return;
  }
  const registration = await registerWorker();
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodeVapidKey(vapidPublicKey),
    });
  }
  await reconcileSubscription(root, subscription);
  setControlState(root, "enabled");
}

async function disablePush(root) {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  let publicId = localStorage.getItem(SUBSCRIPTION_STORAGE_KEY);
  if (!publicId && subscription) {
    publicId = await reconcileSubscription(root, subscription);
  }
  if (publicId) {
    const url = root.dataset.unsubscribeUrlTemplate.replace(UUID_PLACEHOLDER, publicId);
    await jsonRequest(root, url, { method: "POST" });
  }
  if (subscription) await subscription.unsubscribe();
  localStorage.removeItem(SUBSCRIPTION_STORAGE_KEY);
  setControlState(root, "disabled");
}

function startFallbackPolling(root) {
  let cursor = null;
  let bootstrapped = false;
  let timer = null;

  const poll = async () => {
    if (document.hidden || root.dataset.pushState === "enabled") return;
    const url = new URL(root.dataset.pollUrl, window.location.origin);
    if (cursor) url.searchParams.set("cursor", cursor);
    try {
      const payload = await jsonRequest(root, url.href);
      if (!payload) return;
      cursor = payload.cursor || cursor;
      if (bootstrapped) {
        (payload.events || []).forEach((event) => announceEvent(root, event.public_id));
      }
      bootstrapped = true;
    } catch {
      // Le polling est un filet de sécurité silencieux ; le prochain cycle réessaiera.
    }
  };

  const schedule = () => {
    window.clearInterval(timer);
    if (!document.hidden) {
      poll();
      timer = window.setInterval(poll, POLL_INTERVAL_MS);
    }
  };
  document.addEventListener("visibilitychange", schedule);
  schedule();
}

async function boot(root) {
  setControlState(root, "loading");
  startFallbackPolling(root);
  if (!pushSupported()) {
    setControlState(root, "unsupported");
    return;
  }
  if (Notification.permission === "denied") {
    setControlState(root, "denied");
    return;
  }

  try {
    const state = await jsonRequest(root, root.dataset.stateUrl);
    if (!state.enabled || !state.configured || !state.vapid_public_key) {
      setControlState(root, "unavailable");
      return;
    }
    root.dataset.vapidPublicKey = state.vapid_public_key;
    const registration = await registerWorker();
    const subscription = await registration.pushManager.getSubscription();
    if (Notification.permission === "granted" && subscription) {
      await reconcileSubscription(root, subscription);
      setControlState(root, "enabled");
    } else {
      setControlState(root, "disabled");
    }
  } catch {
    setControlState(root, "error");
  }

  root.querySelector("[data-push-toggle]")?.addEventListener("click", async () => {
    const action = root.querySelector("[data-push-toggle]")?.dataset.action;
    setControlState(root, "loading");
    try {
      if (action === "disable") {
        await disablePush(root);
      } else {
        await enablePush(root, root.dataset.vapidPublicKey);
      }
    } catch {
      setControlState(root, "error");
      window.preniumToast?.("Impossible de modifier les notifications sur cet appareil.", "error");
    }
  });
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.type !== "atelier-notification") return;
    const root = document.querySelector("[data-atelier-notifications]");
    if (root) announceEvent(root, event.data.eventPublicId);
  });
}

const root = document.querySelector("[data-atelier-notifications]");
if (root) boot(root);
