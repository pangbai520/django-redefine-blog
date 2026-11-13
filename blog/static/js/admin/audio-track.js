(function () {
  const bindAudioLimit = () => {
    const input = document.getElementById("id_audio_file");
    if (!input || input.dataset.sizeLimitBound === "true") return;

    const maxBytes = Number.parseInt(input.dataset.maxBytes || "0", 10);
    const message = input.dataset.sizeError || "The selected audio file is too large.";
    if (!Number.isFinite(maxBytes) || maxBytes <= 0) return;

    input.dataset.sizeLimitBound = "true";
    const notice = document.createElement("p");
    notice.className = "errornote audio-size-error";
    notice.hidden = true;
    input.insertAdjacentElement("afterend", notice);

    const validate = () => {
      const file = input.files && input.files[0];
      const error = Boolean(file && file.size > maxBytes);
      input.setCustomValidity(error ? message : "");
      notice.textContent = error ? message : "";
      notice.hidden = !error;
      return !error;
    };

    input.addEventListener("change", () => {
      if (!validate()) input.reportValidity();
    });
    input.form?.addEventListener("submit", (event) => {
      if (validate()) return;
      event.preventDefault();
      input.reportValidity();
      input.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAudioLimit, { once: true });
  } else {
    bindAudioLimit();
  }
})();
