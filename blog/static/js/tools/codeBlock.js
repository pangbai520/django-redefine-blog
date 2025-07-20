const languageFromFigure = (figure) => {
  if (figure.dataset.language) return figure.dataset.language;
  const ignored = new Set(["iseeu", "highlight"]);
  return [...figure.classList].find((name) => !ignored.has(name)) || "plaintext";
};

const escapeHtml = (value) => value
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;")
  .replace(/'/g, "&#39;");

/* split highlighted markup into Hexo-style lines, so Redefine's gutters and folding still align */
const splitHighlightedHtml = (html, lineCount) => {
  const fragment = document.createElement("div");
  fragment.innerHTML = html;
  const output = [""];
  const openElements = [];

  const openTag = (element) => {
    const attributes = [...element.attributes]
      .map(({ name, value }) => ` ${name}="${escapeHtml(value)}"`)
      .join("");
    return `<${element.tagName.toLowerCase()}${attributes}>`;
  };

  const closeOpenElements = () => {
    for (let index = openElements.length - 1; index >= 0; index -= 1) {
      output[output.length - 1] += `</${openElements[index].tagName.toLowerCase()}>`;
    }
  };

  const reopenElements = () => {
    openElements.forEach((element) => {
      output[output.length - 1] += openTag(element);
    });
  };

  const visit = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      node.data.split("\n").forEach((part, index, parts) => {
        output[output.length - 1] += escapeHtml(part);
        if (index < parts.length - 1) {
          closeOpenElements();
          output.push("");
          reopenElements();
        }
      });
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;

    output[output.length - 1] += openTag(node);
    openElements.push(node);
    node.childNodes.forEach(visit);
    openElements.pop();
    output[output.length - 1] += `</${node.tagName.toLowerCase()}>`;
  };

  fragment.childNodes.forEach(visit);
  closeOpenElements();
  while (output.length < lineCount) output.push("");
  return output.slice(0, lineCount);
};

const highlightLines = (figure) => {
  if (figure.dataset.highlighted === "true" || !window.hljs) return;

  const lines = [...figure.querySelectorAll(".code .line")];
  if (!lines.length) return;

  const language = languageFromFigure(figure);
  const registeredLanguage = window.hljs.getLanguage(language)
    ? language
    : window.hljs.getLanguage(language === "text" ? "plaintext" : "text")
      ? language === "text" ? "plaintext" : "text"
      : null;

  const source = lines
    .map((line) => line.textContent === " " ? "" : line.textContent)
    .join("\n");
  if (!registeredLanguage || registeredLanguage === "plaintext") {
    figure.dataset.highlighted = "true";
    return;
  }

  try {
    const highlighted = window.hljs.highlight(source, {
      language: registeredLanguage,
      ignoreIllegals: true,
    }).value;
    splitHighlightedHtml(highlighted, lines.length).forEach((html, index) => {
      lines[index].innerHTML = html;
    });
  } catch (error) {
    // leave plain code intact when a grammar is unknown, so highlighting cannot break an article
    lines.forEach((line, index) => {
      line.textContent = source.split("\n")[index] || "";
    });
  }

  figure.dataset.highlighted = "true";
};

const copyText = async (value) => {
  if (globalThis.navigator?.clipboard?.writeText) {
    await globalThis.navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand?.("copy");
  textarea.remove();
  if (!copied) throw new Error("Clipboard API is unavailable");
};

const bindControls = (container) => {
  const copyButton = container.querySelector(".copy-button");
  const foldButton = container.querySelector(".fold-button");

  if (copyButton && document.documentElement.dataset.codeBlockCopy === "false") {
    copyButton.hidden = true;
  }

  if (copyButton && copyButton.dataset.bound !== "true") {
    copyButton.addEventListener("click", async () => {
      const code = [...container.querySelectorAll(".code .line")]
        .map((line) => line.textContent)
        .join("\n");
      try {
        await copyText(code);
        const icon = copyButton.querySelector("i");
        if (icon) icon.className = "fa-regular fa-check";
        setTimeout(() => {
          if (icon) icon.className = "fa-regular fa-copy";
        }, 1000);
      } catch (error) {
        console.warn("Unable to copy code block", error);
      }
    });
    copyButton.dataset.bound = "true";
  }

  if (foldButton && foldButton.dataset.bound !== "true") {
    foldButton.addEventListener("click", () => {
      container.classList.toggle("folded");
      const icon = foldButton.querySelector("i");
      if (icon) {
        icon.className = container.classList.contains("folded")
          ? "fa-solid fa-chevron-up"
          : "fa-solid fa-chevron-down";
      }
    });
    foldButton.dataset.bound = "true";
  }
};

const initCopyCode = () => {
  document.querySelectorAll(".code-container").forEach((codeContainer) => {
    codeContainer.querySelectorAll("figure.highlight").forEach(highlightLines);
    const controls = codeContainer.querySelector(".highlight-container");
    if (controls) bindControls(controls);
  });
};

export default initCopyCode;
