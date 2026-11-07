(function () {
  "use strict";

  var config = window.redefineEditorImages;
  if (!config) return;

  var labels = config.labels || {};
  var activeEditor = null;
  var modal = null;
  var grid = null;
  var moreButton = null;
  var nextPage = 1;
  var draftId = createDraftId();
  var uploadedInDraft = false;
  var submitting = false;

  function createDraftId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (char) {
      var value = Math.floor(Math.random() * 16);
      var digit = char === "x" ? value : (value & 3) | 8;
      return digit.toString(16);
    });
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function imageFiles(fileList) {
    return Array.from(fileList || []).filter(function (file) {
      return file && file.type && file.type.indexOf("image/") === 0;
    });
  }

  function editorFor(wrapper) {
    var codeMirror = wrapper.querySelector(".CodeMirror");
    return codeMirror && codeMirror.CodeMirror;
  }

  function imageMarkdown(name, url) {
    var alt = (name || "image")
      .replace(/\.[^.]+$/, "")
      .replace(/[\[\]\r\n]/g, " ")
      .trim();
    return "![" + (alt || "image") + "](" + url + ")";
  }

  function insertImage(editor, name, url) {
    if (!editor) return;
    var cursor = editor.getCursor();
    var prefix = cursor.ch ? "\n" : "";
    editor.replaceSelection(prefix + imageMarkdown(name, url) + "\n");
    editor.focus();
  }

  function setStatus(tools, message, failed) {
    var status = tools.querySelector(".editor-image-status");
    status.textContent = message || "";
    status.classList.toggle("errornote", Boolean(failed));
  }

  async function uploadFile(file, editor, tools) {
    var data = new FormData();
    data.append("editormd-image-file", file, file.name || "pasted-image.png");
    data.append("draft_id", draftId);
    setStatus(tools, labels.uploading || "Uploading…", false);
    var response = await fetch(config.uploadUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" },
      body: data,
    });
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok || !payload.success || !payload.url) {
      throw new Error(payload.message || payload.detail || labels.failed || "Upload failed");
    }
    insertImage(editor, file.name, payload.url);
    uploadedInDraft = true;
    setStatus(tools, "", false);
  }

  async function uploadFiles(files, editor, tools) {
    tools.classList.add("is-uploading");
    try {
      for (var index = 0; index < files.length; index += 1) {
        await uploadFile(files[index], editor, tools);
      }
    } catch (error) {
      setStatus(tools, error.message || labels.failed || "Upload failed", true);
    } finally {
      tools.classList.remove("is-uploading");
    }
  }

  function makeButton(text, className) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = text;
    return button;
  }

  function attachTools(wrapper) {
    if (wrapper.dataset.imageToolsReady === "true") return;
    var editor = editorFor(wrapper);
    if (!editor) return;
    wrapper.dataset.imageToolsReady = "true";

    var tools = document.createElement("div");
    tools.className = "editor-image-tools";
    var upload = makeButton(labels.upload || "Upload image", "button editor-image-upload");
    var library = makeButton(labels.library || "Image library", "button editor-image-library");
    var input = document.createElement("input");
    input.type = "file";
    input.accept = "image/jpeg,image/png,image/gif,image/webp";
    input.multiple = true;
    input.hidden = true;
    var hint = document.createElement("span");
    hint.className = "editor-image-hint";
    hint.textContent = labels.hint || "Paste or drop images into the editor.";
    var status = document.createElement("span");
    status.className = "editor-image-status";
    tools.append(upload, library, input, hint, status);
    wrapper.before(tools);

    upload.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      var files = imageFiles(input.files);
      if (files.length) uploadFiles(files, editor, tools);
      input.value = "";
    });
    library.addEventListener("click", function () { openLibrary(editor); });

    wrapper.addEventListener("paste", function (event) {
      var files = imageFiles(event.clipboardData && event.clipboardData.files);
      if (!files.length && event.clipboardData && event.clipboardData.items) {
        files = Array.from(event.clipboardData.items)
          .filter(function (item) { return item.type.indexOf("image/") === 0; })
          .map(function (item) { return item.getAsFile(); })
          .filter(Boolean);
      }
      if (!files.length) return;
      event.preventDefault();
      uploadFiles(files, editor, tools);
    }, true);

    wrapper.addEventListener("dragover", function (event) {
      if (!imageFiles(event.dataTransfer && event.dataTransfer.files).length) return;
      event.preventDefault();
      wrapper.classList.add("editor-image-dragging");
    });
    wrapper.addEventListener("dragleave", function () {
      wrapper.classList.remove("editor-image-dragging");
    });
    wrapper.addEventListener("drop", function (event) {
      var files = imageFiles(event.dataTransfer && event.dataTransfer.files);
      wrapper.classList.remove("editor-image-dragging");
      if (!files.length) return;
      event.preventDefault();
      uploadFiles(files, editor, tools);
    });
  }

  function buildModal() {
    if (modal) return;
    modal = document.createElement("div");
    modal.className = "editor-image-modal";
    modal.hidden = true;
    var dialog = document.createElement("section");
    dialog.className = "editor-image-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    var header = document.createElement("header");
    var title = document.createElement("h2");
    title.textContent = labels.library || "Image library";
    var close = makeButton(labels.close || "Close", "button editor-image-close");
    header.append(title, close);
    grid = document.createElement("div");
    grid.className = "editor-image-grid";
    moreButton = makeButton(labels.more || "Load more", "button editor-image-more");
    dialog.append(header, grid, moreButton);
    modal.append(dialog);
    document.body.append(modal);
    close.addEventListener("click", closeLibrary);
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeLibrary();
    });
    moreButton.addEventListener("click", function () { loadImages(nextPage, true); });
  }

  function closeLibrary() {
    if (modal) modal.hidden = true;
  }

  function usedText(count) {
    return (labels.used || "This image is used %(count)s time(s).")
      .replace("%(count)s", String(count));
  }

  function renderImage(image) {
    var card = document.createElement("article");
    card.className = "editor-image-card";
    var insert = makeButton("", "editor-image-insert");
    insert.title = labels.insert || "Insert image";
    var preview = document.createElement("img");
    preview.src = image.url;
    preview.alt = image.name;
    preview.loading = "lazy";
    var name = document.createElement("span");
    name.textContent = image.name;
    insert.append(preview, name);
    insert.addEventListener("click", function () {
      insertImage(activeEditor, image.name, image.url);
      closeLibrary();
    });
    card.append(insert);
    if (!image.deletable) {
      var used = document.createElement("small");
      if (image.ref_count) used.textContent = usedText(image.ref_count);
      card.append(used);
    } else {
      var remove = makeButton(labels.delete || "Delete image", "button editor-image-delete");
      remove.addEventListener("click", async function () {
        if (!window.confirm(labels.delete || "Delete image")) return;
        var response = await fetch(image.delete_url, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" },
        });
        var payload = await response.json().catch(function () { return {}; });
        if (!response.ok) {
          window.alert(payload.detail || labels.failed || "Delete failed");
          return;
        }
        card.remove();
      });
      card.append(remove);
    }
    grid.append(card);
  }

  async function loadImages(page, append) {
    moreButton.disabled = true;
    var response = await fetch(config.listUrl + "?page=" + page, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      grid.textContent = payload.detail || labels.failed || "Unable to load images";
      moreButton.hidden = true;
      return;
    }
    if (!append) grid.replaceChildren();
    (payload.images || []).forEach(renderImage);
    if (!grid.children.length) grid.textContent = labels.empty || "No article images have been uploaded yet.";
    nextPage = page + 1;
    moreButton.hidden = !payload.has_next;
    moreButton.disabled = false;
  }

  function openLibrary(editor) {
    activeEditor = editor;
    buildModal();
    modal.hidden = false;
    loadImages(1, false);
  }

  function addFilePreviews() {
    ["thumbnail", "cover", "banner"].forEach(function (field) {
      var row = document.querySelector(".field-" + field);
      var input = row && row.querySelector('input[type="file"]');
      if (!row || !input || row.querySelector(".article-file-preview")) return;
      var preview = document.createElement("img");
      preview.className = "article-file-preview";
      preview.alt = "";
      var current = row.querySelector("a[href]");
      if (current) preview.src = current.href;
      else preview.hidden = true;
      input.after(preview);
      input.addEventListener("change", function () {
        var file = imageFiles(input.files)[0];
        if (!file) return;
        preview.src = URL.createObjectURL(file);
        preview.hidden = false;
      });
    });
  }

  function discoverEditors() {
    document.querySelectorAll(".wmd-wrapper").forEach(attachTools);
    addFilePreviews();
  }

  function abandonDraft() {
    if (!uploadedInDraft || submitting || !config.abandonUrl) return;
    var data = new FormData();
    data.append("csrfmiddlewaretoken", csrfToken());
    data.append("draft_id", draftId);
    if (navigator.sendBeacon) {
      navigator.sendBeacon(config.abandonUrl, data);
      return;
    }
    fetch(config.abandonUrl, {
      method: "POST",
      credentials: "same-origin",
      body: data,
      keepalive: true,
    });
  }

  var observer = new MutationObserver(discoverEditors);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", discoverEditors);
  document.addEventListener("submit", function () { submitting = true; }, true);
  window.addEventListener("pagehide", abandonDraft);
  window.setTimeout(discoverEditors, 100);
  window.setTimeout(discoverEditors, 500);
})();
