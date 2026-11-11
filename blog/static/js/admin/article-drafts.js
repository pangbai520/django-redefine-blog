(function () {
  "use strict";

  var KEY_PREFIX = "django-redefine:article-draft:v1:";
  var SUBMIT_KEY = "django-redefine:article-draft-submit:v1";
  var IGNORE_KEY = "django-redefine:article-draft-ignore:v1";
  var SAVE_DELAY = 600;
  var FIELD_NAMES = [
    "title",
    "writer",
    "excerpt",
    "content",
    "is_published",
    "show_excerpt",
    "expires_at_0",
    "expires_at_1",
    "created_at_0",
    "created_at_1",
    "updated_at_0",
    "updated_at_1",
    "sticky",
    "copyright_override_enabled",
    "copyright_override_type",
    "show_comment",
    "show_reaction",
    "category",
    "tags",
    "writer_avatar-clear",
    "thumbnail-clear",
    "cover-clear",
    "banner-clear",
  ];

  function readJson(storage, key) {
    try {
      return JSON.parse(storage.getItem(key) || "null");
    } catch (error) {
      return null;
    }
  }

  function removeItem(storage, key) {
    try {
      storage.removeItem(key);
    } catch (error) {
      // Storage can be disabled by browser privacy settings.
    }
  }

  function readItem(storage, key) {
    try {
      return storage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function clearSavedDraft() {
    if (
      !document.body.classList.contains("app-blog") ||
      !document.body.classList.contains("model-articlemodel")
    ) {
      return;
    }
    var marker = readJson(sessionStorage, SUBMIT_KEY);
    if (!marker || !marker.key || !marker.submittedAt) return;
    if (Date.now() - marker.submittedAt > 10 * 60 * 1000) {
      removeItem(sessionStorage, SUBMIT_KEY);
      return;
    }
    if (!document.querySelector(".messagelist .success")) return;
    removeItem(localStorage, marker.key);
    removeItem(sessionStorage, SUBMIT_KEY);
    removeItem(sessionStorage, IGNORE_KEY);
  }

  clearSavedDraft();

  if (
    !document.body.classList.contains("app-blog") ||
    !document.body.classList.contains("model-articlemodel") ||
    !document.body.classList.contains("change-form")
  ) {
    return;
  }

  var config = window.redefineArticleDrafts || {};
  var labels = config.labels || {};
  var form = document.querySelector("#articlemodel_form");
  if (!form) return;

  var draftKey = KEY_PREFIX + window.location.pathname;
  var saveTimer = null;
  var submitting = false;
  var baseline = "";

  function editor() {
    var element = form.querySelector(".CodeMirror");
    return element && element.CodeMirror;
  }

  function readField(name) {
    if (name === "content" && editor()) return editor().getValue();
    var field = form.elements.namedItem(name);
    if (!field) return null;
    if (field.type === "checkbox") return Boolean(field.checked);
    if (field.multiple) {
      return Array.from(field.options)
        .filter(function (option) { return option.selected; })
        .map(function (option) { return option.value; });
    }
    return field.value;
  }

  function fields() {
    var values = {};
    FIELD_NAMES.forEach(function (name) {
      var value = readField(name);
      if (value !== null) values[name] = value;
    });
    return values;
  }

  function fieldString() {
    return JSON.stringify(fields());
  }

  function writeField(name, value) {
    var field = form.elements.namedItem(name);
    if (!field) return;
    if (field.type === "checkbox") field.checked = Boolean(value);
    else if (field.multiple) {
      var selected = Array.isArray(value) ? value.map(String) : [];
      Array.from(field.options).forEach(function (option) {
        option.selected = selected.indexOf(option.value) !== -1;
      });
    }
    else field.value = value == null ? "" : String(value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function restoreDraft(draft) {
    Object.keys(draft.fields || {}).forEach(function (name) {
      if (name === "content" && editor()) {
        editor().setValue(String(draft.fields[name] || ""));
        var textarea = form.elements.namedItem("content");
        if (textarea) textarea.value = String(draft.fields[name] || "");
        return;
      }
      writeField(name, draft.fields[name]);
    });
  }

  function showNotice(message) {
    var messages = document.querySelector("ul.messagelist");
    if (!messages) {
      messages = document.createElement("ul");
      messages.className = "messagelist";
      var content = document.querySelector("#content");
      if (content && content.parentNode) content.parentNode.insertBefore(messages, content);
    }
    if (!messages) return;
    var item = document.createElement("li");
    item.className = "info";
    item.textContent = message;
    messages.append(item);
  }

  function saveDraft() {
    saveTimer = null;
    var draft = {
      version: 1,
      updatedAt: Date.now(),
      fields: fields(),
    };
    try {
      localStorage.setItem(draftKey, JSON.stringify(draft));
    } catch (error) {
      // The editor remains usable when storage is unavailable or full.
    }
    return draft;
  }

  function scheduleSave() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(saveDraft, SAVE_DELAY);
  }

  function markSubmit() {
    var draft = saveDraft();
    try {
      sessionStorage.setItem(
        SUBMIT_KEY,
        JSON.stringify({ key: draftKey, submittedAt: Date.now(), draftAt: draft.updatedAt }),
      );
    } catch (error) {
      // A stored draft is still useful even without the submit marker.
    }
    submitting = true;
  }

  function init(attempt) {
    if (!editor() && attempt < 20) {
      window.setTimeout(function () { init(attempt + 1); }, 100);
      return;
    }

    baseline = fieldString();
    var draft = readJson(localStorage, draftKey);
    var ignored = readItem(sessionStorage, IGNORE_KEY);
    if (
      draft &&
      draft.fields &&
      JSON.stringify(draft.fields) !== baseline &&
      ignored !== String(draft.updatedAt)
    ) {
      var time = new Date(draft.updatedAt).toLocaleString();
      var question = (labels.restore || "An unsaved article draft from %(time)s was found. Restore it?")
        .replace("%(time)s", time);
      if (window.confirm(question)) {
        restoreDraft(draft);
        showNotice(
          labels.restored ||
          "Draft restored. Select local files such as the cover again before saving.",
        );
      } else {
        try {
          sessionStorage.setItem(IGNORE_KEY, String(draft.updatedAt));
        } catch (error) {
          // Repeated prompts are preferable to deleting a draft silently.
        }
      }
    }

    form.addEventListener("input", scheduleSave);
    form.addEventListener("change", scheduleSave);
    form.addEventListener("submit", markSubmit);
    if (editor()) editor().on("change", scheduleSave);
  }

  window.addEventListener("beforeunload", function (event) {
    if (submitting || fieldString() === baseline) return;
    saveDraft();
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("pageshow", function () { submitting = false; });
  window.addEventListener("pagehide", function () {
    if (!submitting && fieldString() !== baseline) saveDraft();
  });
  init(0);
})();
