(function () {
  var form = document.querySelector("[data-register-form]");
  if (!form || form.dataset.ready === "true") return;
  form.dataset.ready = "true";
  form.addEventListener("submit", function () {
    var button = form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    button.disabled = true;
    button.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i><span>' +
      (form.dataset.sendingLabel || "Sending verification email…") + '</span>';
  });
})();
