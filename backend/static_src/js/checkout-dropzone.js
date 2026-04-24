(function () {
  function zoneFromEvent(event) {
    if (!event.target || !event.target.closest) {
      return null;
    }
    return event.target.closest(".dropzone") || event.target.closest(".checkout-dropzone-dui");
  }

  document.addEventListener("dragover", function (event) {
    const zone = zoneFromEvent(event);
    if (!zone) {
      return;
    }
    event.preventDefault();
    zone.classList.add("is-dragover");
  });

  document.addEventListener("dragleave", function (event) {
    const zone = zoneFromEvent(event);
    if (!zone) {
      return;
    }
    zone.classList.remove("is-dragover");
  });

  document.addEventListener("drop", function (event) {
    const zone = zoneFromEvent(event);
    if (!zone) {
      return;
    }
    event.preventDefault();
    zone.classList.remove("is-dragover");
  });
})();
