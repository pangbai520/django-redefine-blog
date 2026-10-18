(function () {
  if (!window.theme?.plugins?.mermaid?.enable || !window.mermaid) return;

  const selector = ".mermaid";
  let renderSequence = 0;
  let renderQueue = Promise.resolve();

  const configuredTheme = () => {
    const mode = document.documentElement.getAttribute("data-theme");
    return mode === "dark"
      ? window.theme?.mermaid?.style?.dark || "dark"
      : window.theme?.mermaid?.style?.light || "default";
  };

  const saveSource = (element) => {
    if (!element.hasAttribute("data-original-code")) {
      element.setAttribute("data-original-code", element.textContent || "");
    }
  };

  const restoreSource = (element) => {
    saveSource(element);
    element.removeAttribute("data-processed");
    element.textContent = element.getAttribute("data-original-code") || "";
  };

  const render = (themeName = configuredTheme()) => {
    const sequence = ++renderSequence;
    renderQueue = renderQueue.catch(() => {}).then(async () => {
      // keep only the newest render request, so rapid mode changes cannot restore stale SVG output
      if (sequence !== renderSequence) return;
      const nodes = [...document.querySelectorAll(selector)];
      if (!nodes.length) return;

      nodes.forEach(restoreSource);
      window.mermaid.initialize({ startOnLoad: false, theme: themeName });
      try {
        await window.mermaid.run({ nodes, suppressErrors: true });
      } catch (error) {
        if (sequence === renderSequence) {
          console.error("Mermaid failed to render", error);
        }
      }
    });
    return renderQueue;
  };

  window.redefineMermaid = { render };

  // let main.refresh() own page changes and expose this bridge to the mode switch,
  // so both paths render with the same active palette
})();
