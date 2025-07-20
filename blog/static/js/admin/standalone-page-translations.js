(function () {
  "use strict";

  const toolbar = [
    "undo", "redo", "|",
    "bold", "del", "italic", "quote", "ucwords", "uppercase", "lowercase", "|",
    "h1", "h2", "h3", "h5", "h6", "|",
    "list-ul", "list-ol", "hr", "|",
    "link", "reference-link", "image", "code", "preformatted-text", "code-block",
    "table", "datetime", "emoji", "html-entities", "pagebreak", "goto-line", "|",
    "help", "info", "||", "preview", "watch", "fullscreen",
  ];

  function initializeEditor(textarea) {
    if (
      !textarea ||
      !textarea.id ||
      textarea.id.includes("__prefix__") ||
      textarea.dataset.markdownEditorReady === "true"
    ) {
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.id = `${textarea.id}-wmd-wrapper`;
    wrapper.className = "wmd-wrapper standalone-page-translation-editor";
    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.appendChild(textarea);
    textarea.dataset.markdownEditorReady = "true";

    window.editormd(wrapper.id, {
      watch: false,
      lineNumbers: false,
      lineWrapping: false,
      width: "100%",
      height: 500,
      autoFocus: false,
      syncScrolling: "single",
      path: textarea.dataset.libraryPath,
      theme: "default",
      previewTheme: "default",
      editorTheme: "default",
      saveHTMLToTextarea: false,
      toolbarAutoFixed: false,
      searchReplace: true,
      emoji: true,
      tex: true,
      taskList: false,
      flowChart: true,
      sequenceDiagram: true,
      imageUpload: true,
      imageFormats: ["jpg", "jpeg", "png", "gif", "webp"],
      imageUploadURL: textarea.dataset.uploadUrl,
      toolbarIcons: function () {
        return toolbar;
      },
    });
  }

  function initializeEditors(root) {
    root.querySelectorAll("textarea.standalone-page-markdown-source").forEach(initializeEditor);
  }

  let loadAttempts = 0;

  function start() {
    if (typeof window.editormd !== "function") {
      loadAttempts += 1;
      if (loadAttempts >= 200) return;
      window.setTimeout(start, 25);
      return;
    }
    initializeEditors(document);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }

  document.addEventListener("formset:added", function (event) {
    if (event.detail && event.detail.formsetName === "translations") {
      initializeEditors(event.target);
    }
  });

  if (window.django && window.django.jQuery) {
    window.django.jQuery(document).on("formset:added", function (_event, row, formsetName) {
      if (formsetName === "translations") {
        initializeEditors(row.get(0));
      }
    });
  }
})();
