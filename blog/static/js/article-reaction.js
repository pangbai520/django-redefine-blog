(function () {
  "use strict";

  var STORAGE_KEY = "WALINE_REACTION";

  function storage() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
    } catch (_error) {
      return {};
    }
  }

  function saveStorage(value) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch (_error) {
      // Voting still works when storage is unavailable.
    }
  }

  function csrfToken(root) {
    var input = root.parentElement.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function init(root) {
    if (root.dataset.ready === "true") return;
    root.dataset.ready = "true";

    var items = Array.from(root.querySelectorAll(".wl-reaction-item"));
    var path = root.dataset.path;
    var active = storage()[path];
    var busy = false;
    var controller = new AbortController();

    function render(counts, selected) {
      items.forEach(function (item, index) {
        item.classList.toggle("active", selected === index);
        item.querySelector(".wl-reaction-votes").textContent = counts[index] || 0;
      });
    }

    function setLoading(index, loading) {
      var item = items[index];
      item.querySelector(".wl-reaction-loading").hidden = !loading;
      item.querySelector(".wl-reaction-votes").hidden = loading;
      root.setAttribute("aria-busy", loading ? "true" : "false");
    }

    function remember(selected) {
      var reactions = storage();
      if (selected == null) delete reactions[path];
      else reactions[path] = selected;
      saveStorage(reactions);
    }

    function load() {
      fetch(root.dataset.api, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: controller.signal
      })
        .then(function (response) {
          if (!response.ok) throw new Error("Unable to load article reactions");
          return response.json();
        })
        .then(function (data) {
          active = Number.isInteger(data.active) ? data.active : active;
          remember(active);
          render(data.counts || [], active);
        })
        .catch(function (error) {
          if (error.name !== "AbortError") console.error(error);
        });
    }

    function vote(index) {
      if (busy) return;
      busy = true;
      setLoading(index, true);
      fetch(root.dataset.api, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(root)
        },
        credentials: "same-origin",
        body: JSON.stringify({ index: index }),
        signal: controller.signal
      })
        .then(function (response) {
          if (!response.ok) throw new Error("Unable to update article reaction");
          return response.json();
        })
        .then(function (data) {
          active = Number.isInteger(data.active) ? data.active : null;
          remember(active);
          render(data.counts || [], active);
        })
        .catch(function (error) {
          if (error.name !== "AbortError") console.error(error);
        })
        .finally(function () {
          busy = false;
          setLoading(index, false);
        });
    }

    items.forEach(function (item, index) {
      item.addEventListener("click", function () { vote(index); });
    });

    root._reactionCleanup = function () { controller.abort(); };
    render([], Number.isInteger(active) ? active : null);
    load();
  }

  window.__articleReactionCleanup?.();
  window.__articleReactionCleanup = function () {
    document.querySelectorAll("[data-article-reaction]").forEach(function (root) {
      root._reactionCleanup?.();
    });
  };

  document.querySelectorAll("[data-article-reaction]").forEach(init);
  if (!window.__articleReactionHook && window.swup?.hooks) {
    window.__articleReactionHook = true;
    window.swup.hooks.on("visit:start", function () {
      window.__articleReactionCleanup?.();
    });
  }
})();
