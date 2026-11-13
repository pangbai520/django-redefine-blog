(function () {
  function render(scope) {
    if (!window.turnstile) return;
    (scope || document).querySelectorAll("[data-turnstile]").forEach(function (node) {
      if (node.dataset.turnstileId) return;
      var widgetId = window.turnstile.render(node, {
        sitekey: node.dataset.sitekey,
        action: node.dataset.action,
        theme: "auto"
      });
      node.dataset.turnstileId = String(widgetId);
    });
  }

  function reset(scope) {
    if (!window.turnstile) return;
    (scope || document).querySelectorAll("[data-turnstile-id]").forEach(function (node) {
      window.turnstile.reset(node.dataset.turnstileId);
    });
  }

  window.blogTurnstile = { render: render, reset: reset };
  window.blogTurnstileReady = function () { render(document); };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { render(document); }, { once: true });
  } else {
    render(document);
  }
  document.addEventListener("swup:contentReplaced", function () { render(document); });
})();
