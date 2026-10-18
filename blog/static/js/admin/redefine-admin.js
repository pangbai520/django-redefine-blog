(function () {
  "use strict";

  function normalize(value) {
    return (value || "").toLocaleLowerCase().replace(/\s+/g, " ").trim();
  }

  function installConfigurationSearch() {
    if (!document.body.classList.contains("model-siteconfiguration") || !document.body.classList.contains("change-form")) return;

    var form = document.querySelector("#content-main form");
    var firstFieldset = form && form.querySelector("fieldset.module");
    if (!form || !firstFieldset || form.querySelector(".redefine-config-search")) return;

    var toolbar = document.createElement("div");
    toolbar.className = "redefine-config-search";
    toolbar.innerHTML = '<input type="search" autocomplete="off" placeholder="Search settings, fields, or help text…" aria-label="Search configuration"><button type="button">Clear</button>';
    firstFieldset.before(toolbar);

    var empty = document.createElement("p");
    empty.className = "redefine-search-empty";
    empty.hidden = true;
    empty.textContent = "No matching settings.";
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
