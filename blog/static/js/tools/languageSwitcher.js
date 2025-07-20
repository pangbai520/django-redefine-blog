let languageSwitcherController = null;

export default function initLanguageSwitcher() {
  languageSwitcherController?.abort();
  languageSwitcherController = new AbortController();
  const { signal } = languageSwitcherController;

  const trigger = document.querySelector(".tool-language-switch");
  const modal = document.querySelector("[data-language-switcher-modal]");
  const dialog = modal?.querySelector(".language-switcher-dialog");
  const closeButtons = modal?.querySelectorAll("[data-language-switcher-close]") || [];
  if (!trigger || !modal || !dialog) return;

  const firstOption = modal.querySelector(".language-switcher-option");
  const close = () => {
    if (modal.hidden) return;
    modal.classList.remove("is-open");
    document.body.classList.remove("language-switcher-open");
    window.setTimeout(() => {
      modal.hidden = true;
      trigger.focus();
    }, 180);
  };
  const open = () => {
    modal.hidden = false;
    document.body.classList.add("language-switcher-open");
    window.requestAnimationFrame(() => modal.classList.add("is-open"));
    firstOption?.focus();
  };

  trigger.addEventListener("click", open, { signal });
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  }, { signal });
  closeButtons.forEach((button) => button.addEventListener("click", close, { signal }));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) close();
  }, { signal });
}
