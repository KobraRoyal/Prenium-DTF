(function initClientBillingPay() {
  const SDK_PARAM = "sdk";
  const MOUNT_PENDING = "pending";
  const MOUNT_READY = "ready";
  const createOrderLocks = new WeakMap();
  let sdkLoadPromise = null;
  let listenersBound = false;

  function getPayPalConfig(root) {
    const clientId = root?.dataset?.paypalClientId;
    if (!clientId) {
      return null;
    }
    return {
      clientId,
      currency: root.dataset.paypalCurrency || "EUR",
      initiateUrl: root.dataset.paypalInitiateUrl,
      captureUrl: root.dataset.paypalCaptureUrl,
    };
  }

  function loadPayPalSdk(clientId, currency) {
    const expectedMarker = "disable-funding=credit";
    const existingScript = document.querySelector('script[data-prenium-paypal-sdk="1"]');
    if (
      window.paypal
      && existingScript instanceof HTMLScriptElement
      && existingScript.src.includes(expectedMarker)
    ) {
      return Promise.resolve(window.paypal);
    }
    if (sdkLoadPromise) {
      return sdkLoadPromise;
    }
    if (existingScript instanceof HTMLScriptElement) {
      existingScript.remove();
    }
    delete window.paypal;
    sdkLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=${encodeURIComponent(currency)}&intent=capture&components=buttons&disable-funding=credit,paylater,venmo`;
      script.setAttribute("data-prenium-paypal-sdk", "1");
      script.async = true;
      script.onload = () => {
        if (!window.paypal) {
          sdkLoadPromise = null;
          reject(new Error("Le SDK PayPal n’a pas pu être initialisé."));
          return;
        }
        resolve(window.paypal);
      };
      script.onerror = () => {
        sdkLoadPromise = null;
        reject(new Error("Le service PayPal est indisponible."));
      };
      document.head.appendChild(script);
    });
    return sdkLoadPromise;
  }

  function billingShellUrl(root) {
    return root?.dataset?.billingShellUrl || `${window.location.pathname}${window.location.search}`;
  }

  function csrfToken(form) {
    return form.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
  }

  function selectedProvider(form) {
    const selected = form.querySelector('input[name="provider"]:checked');
    if (selected) {
      return selected.value;
    }
    const hidden = form.querySelector('input[name="provider"][type="hidden"]');
    return hidden?.value || "";
  }

  function payDialogForForm(form) {
    return form.closest("dialog.client-billing-pay-dialog");
  }

  function canMountPayPalButtons(form) {
    const dialog = payDialogForForm(form);
    return !(dialog instanceof HTMLDialogElement) || dialog.open;
  }

  function syncProviderChrome(form) {
    const provider = selectedProvider(form);
    const stripeSubmit = form.querySelector("[data-client-billing-stripe-submit]");
    const paypalHost = form.querySelector("[data-paypal-button-host]");
    const isPayPal = provider === "paypal";
    if (stripeSubmit) {
      stripeSubmit.hidden = isPayPal;
    }
    if (paypalHost) {
      paypalHost.hidden = !isPayPal;
    }
  }

  function resetPayPalButtons(form) {
    const container = form.querySelector("[data-paypal-button-container]");
    if (!(container instanceof HTMLElement)) {
      return;
    }
    container.replaceChildren();
    delete container.dataset.paypalMountState;
  }

  function teardownPayPalButtons(form) {
    resetPayPalButtons(form);
    createOrderLocks.delete(form);
  }

  async function createPayPalOrder(form, config) {
    const existing = createOrderLocks.get(form);
    if (existing) {
      return existing;
    }
    const pending = (async () => {
      const body = new FormData(form);
      body.set(SDK_PARAM, "1");
      body.set("provider", "paypal");
      const response = await fetch(config.initiateUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
        body,
      });
      let payload = {};
      try {
        payload = await response.json();
      } catch (_error) {
        payload = {};
      }
      if (!response.ok || !payload.ok || !payload.paypal_order_id) {
        throw new Error(payload.error || "Impossible de démarrer le paiement PayPal.");
      }
      return payload.paypal_order_id;
    })();
    createOrderLocks.set(form, pending);
    try {
      return await pending;
    } finally {
      createOrderLocks.delete(form);
    }
  }

  function buildPayPalButtonOptions(form, config, root) {
    return {
      style: {
        layout: "vertical",
        color: "gold",
        shape: "rect",
        label: "paypal",
      },
      createOrder: () => createPayPalOrder(form, config),
      onApprove: async (data) => {
        const body = new FormData();
        body.set("paypal_order_id", data.orderID);
        body.set("csrfmiddlewaretoken", csrfToken(form));
        const response = await fetch(config.captureUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            Accept: "application/json",
          },
          body,
        });
        let payload = {};
        try {
          payload = await response.json();
        } catch (_error) {
          payload = {};
        }
        if (!response.ok || !payload.ok) {
          window.preniumToast?.(
            payload.error || "Le paiement n’a pas pu être finalisé.",
            "error",
          );
          return;
        }
        const dialog = payDialogForForm(form);
        if (dialog?.open) {
          dialog.close();
        }
        if (payload.redirect_url) {
          window.location.assign(payload.redirect_url);
          return;
        }
        const base = billingShellUrl(root);
        const separator = base.includes("?") ? "&" : "?";
        window.location.assign(`${base}${separator}panel=billing&paid=1`);
      },
      onCancel: () => {
        window.preniumToast?.(
          "Paiement annulé. Vous pouvez réessayer quand vous voulez.",
          "info",
        );
      },
      onError: () => {
        window.preniumToast?.("Une erreur PayPal est survenue.", "error");
      },
    };
  }

  async function renderPayPalButtons(paypal, form, config, container) {
    const root = form.closest("[data-client-billing-pay-root]");
    const buttons = paypal.Buttons(buildPayPalButtonOptions(form, config, root));
    if (!buttons.isEligible()) {
      return false;
    }
    await buttons.render(container);
    return true;
  }

  async function ensurePayPalButtons(form) {
    if (!canMountPayPalButtons(form) || selectedProvider(form) !== "paypal") {
      return;
    }

    const root = form.closest("[data-client-billing-pay-root]");
    const config = getPayPalConfig(root);
    if (!config) {
      return;
    }

    const container = form.querySelector("[data-paypal-button-container]");
    if (!(container instanceof HTMLElement)) {
      return;
    }
    if (
      container.dataset.paypalMountState === MOUNT_PENDING
      || container.dataset.paypalMountState === MOUNT_READY
    ) {
      return;
    }
    container.dataset.paypalMountState = MOUNT_PENDING;

    try {
      const paypal = await loadPayPalSdk(config.clientId, config.currency);
      if (
        container.dataset.paypalMountState !== MOUNT_PENDING
        || !canMountPayPalButtons(form)
        || selectedProvider(form) !== "paypal"
      ) {
        delete container.dataset.paypalMountState;
        return;
      }

      container.replaceChildren();
      const rendered = await renderPayPalButtons(paypal, form, config, container);

      if (!rendered) {
        container.replaceChildren();
        const fallback = document.createElement("p");
        fallback.className = "muted text-sm m-0";
        fallback.textContent = "PayPal n’est pas disponible sur cet appareil.";
        container.appendChild(fallback);
        delete container.dataset.paypalMountState;
        return;
      }

      container.dataset.paypalMountState = MOUNT_READY;
    } catch (error) {
      delete container.dataset.paypalMountState;
      window.preniumToast?.(
        error.message || "Impossible de charger PayPal.",
        "error",
      );
    }
  }

  function handleProviderChange(form) {
    syncProviderChrome(form);
    if (selectedProvider(form) === "paypal") {
      resetPayPalButtons(form);
      ensurePayPalButtons(form);
      return;
    }
    teardownPayPalButtons(form);
  }

  function handleDialogToggle(dialog) {
    const form = dialog.querySelector("[data-client-billing-pay-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    syncProviderChrome(form);
    if (!dialog.open) {
      teardownPayPalButtons(form);
      return;
    }
    if (selectedProvider(form) === "paypal") {
      ensurePayPalButtons(form);
    }
  }

  function bindForms(scope) {
    scope.querySelectorAll("[data-client-billing-pay-form]").forEach((form) => {
      if (!(form instanceof HTMLFormElement) || form.dataset.billingPayBound === "1") {
        return;
      }
      form.dataset.billingPayBound = "1";

      form.querySelectorAll('input[name="provider"]').forEach((input) => {
        input.addEventListener("change", () => handleProviderChange(form));
      });

      form.addEventListener("submit", (event) => {
        if (selectedProvider(form) === "paypal") {
          event.preventDefault();
        }
      });

      syncProviderChrome(form);
    });
  }

  function bindGlobalListeners() {
    if (listenersBound) {
      return;
    }
    listenersBound = true;

    document.addEventListener(
      "toggle",
      (event) => {
        const dialog = event.target;
        if (!(dialog instanceof HTMLDialogElement) || !dialog.classList.contains("client-billing-pay-dialog")) {
          return;
        }
        handleDialogToggle(dialog);
      },
      true,
    );
  }

  function init(scope = document) {
    bindGlobalListeners();
    bindForms(scope);
    scope.querySelectorAll("dialog.client-billing-pay-dialog").forEach((dialog) => {
      if (dialog instanceof HTMLDialogElement && dialog.open) {
        handleDialogToggle(dialog);
      }
    });
  }

  init();

  document.body.addEventListener("htmx:afterSwap", (event) => {
    init(event.target);
  });
})();
