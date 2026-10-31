(function () {
  "use strict";

  function ensureEditorCsrf(form) {
    if (!(form instanceof HTMLFormElement) || !form.classList.contains("editormd-form")) return;
    if (form.querySelector('input[name="csrfmiddlewaretoken"]')) return;
    var token = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (!token || !token.value) return;
    var hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "csrfmiddlewaretoken";
    hidden.value = token.value;
    form.appendChild(hidden);
  }

  document.addEventListener("submit", function (event) {
    ensureEditorCsrf(event.target);
  }, true);

  // Editor.md builds the upload form only after the image dialog opens and
  // immediately submits it when a file is chosen. Inject CSRF at creation time
  // as well, so the iframe upload does not depend on a cancellable submit event.
  new MutationObserver(function (records) {
    records.forEach(function (record) {
      record.addedNodes.forEach(function (node) {
        if (!(node instanceof Element)) return;
        if (node.matches("form.editormd-form")) ensureEditorCsrf(node);
        node.querySelectorAll("form.editormd-form").forEach(ensureEditorCsrf);
      });
    });
  }).observe(document.documentElement, { childList: true, subtree: true });

  function normalize(value) {
    return (value || "").toLocaleLowerCase().replace(/\s+/g, " ").trim();
  }

  function translate(message) {
    return typeof window.gettext === "function" ? window.gettext(message) : message;
  }

  function installConfigurationSearch() {
    if (!document.body.classList.contains("model-siteconfiguration") || !document.body.classList.contains("change-form")) return;

    var form = document.querySelector("#content-main form");
    var firstFieldset = form && form.querySelector("fieldset.module");
    if (!form || !firstFieldset || form.querySelector(".redefine-config-search")) return;

    var toolbar = document.createElement("div");
    toolbar.className = "redefine-config-search";
    var searchLabel = translate("Search settings, fields, or help text…");
    toolbar.innerHTML = '<input type="search" autocomplete="off"><button type="button"></button>';
    toolbar.querySelector("input").placeholder = searchLabel;
    toolbar.querySelector("input").setAttribute("aria-label", translate("Search configuration"));
    toolbar.querySelector("button").textContent = translate("Clear");
    firstFieldset.before(toolbar);

    var empty = document.createElement("p");
    empty.className = "redefine-search-empty";
    empty.hidden = true;
    empty.textContent = translate("No matching settings.");
    toolbar.after(empty);

    var input = toolbar.querySelector("input");
    var fieldsets = Array.from(form.querySelectorAll("fieldset.module"));

    function filterConfiguration() {
      var query = normalize(input.value);
      var visibleFieldsets = 0;

      fieldsets.forEach(function (fieldset) {
        var heading = normalize((fieldset.querySelector("h2, summary") || {}).textContent);
        var headingMatches = query && heading.indexOf(query) !== -1;
        var rows = Array.from(fieldset.querySelectorAll(":scope > .form-row, :scope > details > .form-row"));
        var visibleRows = 0;

        rows.forEach(function (row) {
          var providerHidden = row.dataset.commentProviderHidden === "true";
          var values = Array.from(row.querySelectorAll("input, textarea, select")).map(function (field) {
            if (field.tagName === "SELECT" && field.selectedOptions.length) return field.selectedOptions[0].textContent;
            return field.value;
          }).join(" ");
          var searchable = normalize(row.textContent + " " + values);
          var matches = !providerHidden && (!query || headingMatches || searchable.indexOf(query) !== -1);
          row.hidden = !matches;
          if (matches) visibleRows += 1;
        });

        var visible = !query || headingMatches || visibleRows > 0;
        fieldset.hidden = !visible;
        if (visible) {
          visibleFieldsets += 1;
          var details = fieldset.querySelector("details");
          if (query && details) details.open = true;
        }
      });

      empty.hidden = visibleFieldsets !== 0;
    }

    input.addEventListener("input", filterConfiguration);
    document.addEventListener("admin:comment-provider-change", filterConfiguration);
    toolbar.querySelector("button").addEventListener("click", function () {
      input.value = "";
      filterConfiguration();
      input.focus();
    });

    document.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault();
        input.focus();
      }
    });
  }

  function installGlobalSearchShortcut() {
    if (document.querySelector(".redefine-config-search")) return;
    document.addEventListener("keydown", function (event) {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLocaleLowerCase() !== "k") return;
      var target = document.querySelector("#nav-filter, #searchbar");
      if (!target) return;
      event.preventDefault();
      target.focus();
    });
  }

  function installCollapsibleFilters() {
    document.querySelectorAll("#changelist-filter details[data-filter-title]").forEach(function (filter) {
      var choices = Array.from(filter.querySelectorAll("li"));
      var selected = filter.querySelector("li.selected");

      // the first choice is "All", only open groups that have a real filter applied
      filter.open = Boolean(selected && selected !== choices[0]);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    installConfigurationSearch();
    installGlobalSearchShortcut();
    installCollapsibleFilters();
  });
})();
