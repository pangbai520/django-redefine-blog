import { getStyleStatus, setStyleStatus, styleStatus } from "../themeState.js";

let modeToggleController = null;
let giscusThemeSequence = 0;
let themeTransitionFrame = null;
let activeThemeTransition = null;

const requestThemeFrame = (callback) =>
  typeof window.requestAnimationFrame === "function"
    ? window.requestAnimationFrame(callback)
    : window.setTimeout(callback, 0);

const cancelThemeFrame = (frame) => {
  if (frame === null) return;
  if (typeof window.cancelAnimationFrame === "function") {
    window.cancelAnimationFrame(frame);
  } else {
    window.clearTimeout(frame);
  }
};

const beginThemeSwitch = () => {
  const root = document.documentElement;
  root.classList.add("theme-switching");
  cancelThemeFrame(themeTransitionFrame);
  // keep transitions disabled through one paint, so hundreds of inherited
  // colour transitions cannot make the palette change appear staggered
  themeTransitionFrame = requestThemeFrame(() => {
    themeTransitionFrame = requestThemeFrame(() => {
      root.classList.remove("theme-switching");
      themeTransitionFrame = null;
    });
  });
};

const runThemeSwitch = (update, animate) => {
  const canAnimate =
    animate &&
    typeof document.startViewTransition === "function" &&
    !window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

  if (!canAnimate) {
    beginThemeSwitch();
    update();
    return null;
  }

  cancelThemeFrame(themeTransitionFrame);
  themeTransitionFrame = null;
  activeThemeTransition?.skipTransition?.();
  document.documentElement.classList.add("theme-switching");

  const transition = document.startViewTransition(update);
  activeThemeTransition = transition;
  transition.finished.catch(() => {}).finally(() => {
    if (activeThemeTransition !== transition) return;
    document.documentElement.classList.remove("theme-switching");
    activeThemeTransition = null;
  });
  return transition;
};

const ModeToggle = {
  modeToggleButton_dom: null,
  iconDom: null,
  mermaidLightTheme: null,
  mermaidDarkTheme: null,

  async mermaidInit(theme) {
    await window.redefineMermaid?.render?.(theme);
  },

  enableLightMode(persist = true) {
    return runThemeSwitch(() => {
      document.body.classList.remove("dark-mode");
      document.documentElement.classList.remove("dark", "dark-mode");
      document.body.classList.add("light-mode");
      document.documentElement.classList.add("light", "light-mode");
      document.documentElement.setAttribute("data-theme", "light");
      document.documentElement.style.colorScheme = "light";
      if (this.iconDom) this.iconDom.className = "fa-regular fa-moon";
      styleStatus.isDark = false;
      if (persist) {
        styleStatus.isColorModeExplicit = true;
        setStyleStatus();
      }
      this.mermaidInit(this.mermaidLightTheme);
      this.setGiscusTheme();
    }, persist);
  },

  enableDarkMode(persist = true) {
    return runThemeSwitch(() => {
      document.body.classList.remove("light-mode");
      document.documentElement.classList.remove("light", "light-mode");
      document.body.classList.add("dark-mode");
      document.documentElement.classList.add("dark", "dark-mode");
      document.documentElement.setAttribute("data-theme", "dark");
      document.documentElement.style.colorScheme = "dark";
      if (this.iconDom) this.iconDom.className = "fa-regular fa-brightness";
      styleStatus.isDark = true;
      if (persist) {
        styleStatus.isColorModeExplicit = true;
        setStyleStatus();
      }
      this.mermaidInit(this.mermaidDarkTheme);
      this.setGiscusTheme();
    }, persist);
  },

  async setGiscusTheme(theme) {
    const sequence = ++giscusThemeSequence;
    const container = document.querySelector(".giscus, #giscus-container");
    if (!container) return;

    let giscusFrame = container.querySelector("iframe.giscus-frame");
    for (let attempt = 0; !giscusFrame && attempt < 100; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      if (sequence !== giscusThemeSequence || !document.contains(container)) return;
      giscusFrame = container.querySelector("iframe.giscus-frame");
    }
    if (sequence !== giscusThemeSequence || !giscusFrame?.contentWindow) return;

    theme ??= styleStatus.isDark ? "dark" : "light";
    giscusFrame.contentWindow.postMessage(
      { giscus: { setConfig: { theme } } },
      "https://giscus.app",
    );
  },

  isDarkPrefersColorScheme() {
    return (
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)")
    );
  },

  initModeStatus() {
    const savedStyleStatus = getStyleStatus();

    if (savedStyleStatus?.isColorModeExplicit) {
      savedStyleStatus.isDark
        ? this.enableDarkMode(false)
        : this.enableLightMode(false);
    } else {
      const defaultMode = window.theme?.colors?.default_mode;
      const isDark = defaultMode === "dark" ||
        (defaultMode !== "light" && !!this.isDarkPrefersColorScheme()?.matches);
      isDark
        ? this.enableDarkMode(false)
        : this.enableLightMode(false);
    }
  },

  initModeToggleButton(signal) {
    this.modeToggleButton_dom?.addEventListener("click", () => {
      const isDark = document.body.classList.contains("dark-mode");
      isDark ? this.enableLightMode() : this.enableDarkMode();
    }, { signal });
  },

  initModeAutoTrigger(signal) {
    const defaultMode = window.theme?.colors?.default_mode;
    if (defaultMode === "light" || defaultMode === "dark") return;
    const isDarkMode = this.isDarkPrefersColorScheme();
    isDarkMode?.addEventListener("change", (e) => {
      if (getStyleStatus()?.isColorModeExplicit) return;
      e.matches ? this.enableDarkMode(false) : this.enableLightMode(false);
    }, { signal });
  },

  async init() {
    modeToggleController?.abort();
    modeToggleController = new AbortController();
    const { signal } = modeToggleController;

    this.modeToggleButton_dom = document.querySelector(
      ".tool-dark-light-toggle",
    );
    this.iconDom = document.querySelector(".tool-dark-light-toggle i");
    this.mermaidLightTheme =
      typeof theme.mermaid !== "undefined" &&
      typeof theme.mermaid.style !== "undefined" &&
      typeof theme.mermaid.style.light !== "undefined"
        ? theme.mermaid.style.light
        : "default";
    this.mermaidDarkTheme =
      typeof theme.mermaid !== "undefined" &&
      typeof theme.mermaid.style !== "undefined" &&
      typeof theme.mermaid.style.dark !== "undefined"
        ? theme.mermaid.style.dark
        : "dark";
    this.initModeStatus();
    this.initModeToggleButton(signal);
    this.initModeAutoTrigger(signal);
  },
};

export default function initModeToggle() {
  ModeToggle.init();
}
