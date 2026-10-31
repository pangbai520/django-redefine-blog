(function () {
  "use strict";

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.pendingLabel) return;
    var button = form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i><span></span>';
    button.querySelector("span").textContent = form.dataset.pendingLabel;
  }, true);
})();
