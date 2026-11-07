(function () {
  "use strict";

  var config = window.redefineEditorImages;
  if (!config) return;

  var labels = config.labels || {};
  var activeEditor = null;
  var modal = null;
  var grid = null;
  var moreButton = null;
  var folderList = null;
  var searchInput = null;
  var renameFolderButton = null;
  var deleteFolderButton = null;
  var folders = [];
  var folderSelects = [];
  var activeFolder = "all";
  var searchTerm = "";
  var foldersReady = false;
  var folderRequest = null;
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

  async function postForm(url, values) {
    var data = new FormData();
    Object.keys(values || {}).forEach(function (key) {
      data.append(key, values[key]);
    });
    var response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" },
      body: data,
    });
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      throw new Error(payload.detail || labels.failed || "Request failed");
    }
    return payload;
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
    var folderSelect = tools.querySelector(".editor-image-folder-select");
    data.append("folder_id", folderSelect ? folderSelect.value : "");
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

  function fillFolderSelect(select, selected) {
    var value = selected == null ? "" : String(selected);
    select.replaceChildren();
    var uncategorized = document.createElement("option");
    uncategorized.value = "";
    uncategorized.textContent = labels.uncategorized || "Uncategorized";
    select.append(uncategorized);
    folders.forEach(function (folder) {
      var option = document.createElement("option");
      option.value = String(folder.id);
      option.textContent = folder.name;
      select.append(option);
    });
    select.value = value;
  }

  function refreshFolderSelects() {
    folderSelects = folderSelects.filter(function (select) {
      return select.isConnected;
    });
    folderSelects.forEach(function (select) {
      fillFolderSelect(select, select.value);
    });
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
    var folderSelect = document.createElement("select");
    folderSelect.className = "editor-image-folder-select";
    folderSelect.setAttribute("aria-label", labels.folder || "Folder");
    fillFolderSelect(folderSelect, "");
    folderSelects.push(folderSelect);
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
    tools.append(upload, library, folderSelect, input, hint, status);
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
    var toolbar = document.createElement("form");
    toolbar.className = "editor-image-library-toolbar";
    searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = labels.search || "Search images";
    searchInput.setAttribute("aria-label", labels.search || "Search images");
    var search = makeButton(labels.searchButton || "Search", "button");
    search.type = "submit";
    var newFolder = makeButton(labels.newFolder || "New folder", "button");
    renameFolderButton = makeButton(labels.renameFolder || "Rename", "button");
    deleteFolderButton = makeButton(labels.deleteFolder || "Delete folder", "button editor-folder-delete");
    toolbar.append(searchInput, search, newFolder, renameFolderButton, deleteFolderButton);
    var layout = document.createElement("div");
    layout.className = "editor-image-library-layout";
    folderList = document.createElement("nav");
    folderList.className = "editor-image-folders";
    folderList.setAttribute("aria-label", labels.folders || "Folders");
    var content = document.createElement("section");
    content.className = "editor-image-library-content";
    grid = document.createElement("div");
    grid.className = "editor-image-grid";
    moreButton = makeButton(labels.more || "Load more", "button editor-image-more");
    content.append(grid, moreButton);
    layout.append(folderList, content);
    dialog.append(header, toolbar, layout);
    modal.append(dialog);
    document.body.append(modal);
    close.addEventListener("click", closeLibrary);
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeLibrary();
    });
    moreButton.addEventListener("click", function () { loadImages(nextPage, true); });
    toolbar.addEventListener("submit", function (event) {
      event.preventDefault();
      searchTerm = searchInput.value.trim();
      loadImages(1, false);
    });
    newFolder.addEventListener("click", createFolder);
    renameFolderButton.addEventListener("click", renameFolder);
    deleteFolderButton.addEventListener("click", deleteFolder);
  }

  function closeLibrary() {
    if (modal) modal.hidden = true;
  }

  function usedText(count) {
    return (labels.used || "This image is used %(count)s time(s).")
      .replace("%(count)s", String(count));
  }

  function formatBytes(bytes) {
    var size = Number(bytes || 0);
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
    return (size / (1024 * 1024)).toFixed(1) + " MB";
  }

  function applyFolderData(payload) {
    folders = payload.folders || [];
    config.allImageCount = payload.all_count || 0;
    config.uncategorizedCount = payload.uncategorized_count || 0;
    foldersReady = true;
    refreshFolderSelects();
    renderFolders();
  }

  async function loadFolderMetadata() {
    if (foldersReady) return;
    if (folderRequest) return folderRequest;
    folderRequest = fetch(config.listUrl + "?page=1", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }).then(async function (response) {
      if (response.ok) applyFolderData(await response.json());
    }).finally(function () {
      folderRequest = null;
    });
    return folderRequest;
  }

  function folderUrl(template, folderId) {
    return template.replace(/\/0\//, "/" + folderId + "/");
  }

  function selectedFolder() {
    return folders.find(function (folder) {
      return String(folder.id) === String(activeFolder);
    });
  }

  function folderButton(value, text, count) {
    var button = makeButton("", "editor-image-folder");
    button.classList.toggle("is-active", String(activeFolder) === String(value));
    var label = document.createElement("span");
    label.textContent = text;
    var badge = document.createElement("small");
    badge.textContent = String(count || 0);
    button.append(label, badge);
    button.addEventListener("click", function () {
      activeFolder = String(value);
      renderFolders();
      loadImages(1, false);
    });
    return button;
  }

  function renderFolders() {
    if (!folderList) return;
    folderList.replaceChildren(
      folderButton("all", labels.allImages || "All images", config.allImageCount || 0),
      folderButton(
        "uncategorized",
        labels.uncategorized || "Uncategorized",
        config.uncategorizedCount || 0
      )
    );
    folders.forEach(function (folder) {
      folderList.append(folderButton(folder.id, folder.name, folder.count));
    });
    var hasFolder = Boolean(selectedFolder());
    renameFolderButton.disabled = !hasFolder;
    deleteFolderButton.disabled = !hasFolder;
  }

  async function createFolder() {
    var name = window.prompt(labels.folderName || "Folder name");
    if (!name || !name.trim()) return;
    try {
      var folder = await postForm(config.folderCreateUrl, { name: name });
      activeFolder = String(folder.id);
      await loadImages(1, false);
    } catch (error) {
      window.alert(error.message);
    }
  }

  async function renameFolder() {
    var folder = selectedFolder();
    if (!folder) return;
    var name = window.prompt(labels.folderName || "Folder name", folder.name);
    if (!name || !name.trim() || name.trim() === folder.name) return;
    try {
      await postForm(folderUrl(config.folderRenameUrl, folder.id), { name: name });
      await loadImages(1, false);
    } catch (error) {
      window.alert(error.message);
    }
  }

  async function deleteFolder() {
    var folder = selectedFolder();
    if (!folder) return;
    var message = labels.deleteFolderConfirm || "Delete this folder? Its images will remain uncategorized.";
    if (!window.confirm(message)) return;
    try {
      await postForm(folderUrl(config.folderDeleteUrl, folder.id), {});
      activeFolder = "uncategorized";
      await loadImages(1, false);
    } catch (error) {
      window.alert(error.message);
    }
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
    var meta = document.createElement("small");
    meta.className = "editor-image-meta";
    meta.textContent = (image.width && image.height ? image.width + " × " + image.height + " · " : "") + formatBytes(image.size);
    var move = document.createElement("select");
    move.className = "editor-image-move";
    move.setAttribute("aria-label", labels.moveToFolder || "Move to folder");
    fillFolderSelect(move, image.folder_id);
    move.addEventListener("change", async function () {
      move.disabled = true;
      try {
        await postForm(image.move_url, { folder_id: move.value });
        await loadImages(1, false);
      } catch (error) {
        window.alert(error.message);
        move.disabled = false;
      }
    });
    var actions = document.createElement("div");
    actions.className = "editor-image-card-actions";
    actions.append(move);
    card.append(insert, meta, actions);
    if (!image.deletable) {
      var used = document.createElement("small");
      used.textContent = image.ref_count
        ? usedText(image.ref_count)
        : (labels.inDraft || "Used by an open draft");
      used.className = "editor-image-usage";
      card.append(used);
    } else {
      var remove = makeButton(labels.delete || "Delete image", "button editor-image-delete");
      remove.addEventListener("click", async function () {
        if (!window.confirm(labels.delete || "Delete image")) return;
        try {
          await postForm(image.delete_url, {});
          await loadImages(1, false);
        } catch (error) {
          window.alert(error.message);
        }
      });
      actions.append(remove);
    }
    grid.append(card);
  }

  async function loadImages(page, append) {
    moreButton.disabled = true;
    var params = new URLSearchParams({
      page: String(page),
      folder: String(activeFolder),
    });
    if (searchTerm) params.set("q", searchTerm);
    var response = await fetch(config.listUrl + "?" + params.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      grid.textContent = payload.detail || labels.failed || "Unable to load images";
      moreButton.hidden = true;
      return;
    }
    applyFolderData(payload);
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
    loadFolderMetadata();
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
