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

  const bindPlayerColour = () => {
    const hidden = document.querySelector('input[data-player-colour="true"]');
    if (!hidden || hidden.dataset.colourBound === "true") return;

    const box = hidden.nextElementSibling;
    const picker = box?.querySelector("[data-player-colour-picker]");
    const clear = box?.querySelector("[data-player-colour-clear]");
    if (!box || !picker || !clear) return;

    hidden.dataset.colourBound = "true";
    const showState = () => box.classList.toggle("is-default", !hidden.value);

    picker.addEventListener("input", () => {
      hidden.value = picker.value;
      showState();
    });
    clear.addEventListener("click", () => {
      hidden.value = "";
      showState();
    });
    showState();
  };

  const bindControls = () => {
    bindAudioLimit();
    bindPlayerColour();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindControls, { once: true });
  } else {
    bindControls();
  }
})();
