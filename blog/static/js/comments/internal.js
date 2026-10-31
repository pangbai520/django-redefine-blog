(function () {
  window.__internalCommentsCleanup?.();
  var lifecycleController = new AbortController();
  var lifecycleSignal = lifecycleController.signal;
  var cleanupTasks = [];

  function cleanup() {
    lifecycleController.abort();
    cleanupTasks.splice(0).forEach(function (task) { task(); });
    document.querySelectorAll('[data-auth-modal][data-internal-owned="true"], [data-comment-confirm][data-internal-owned="true"]').forEach(function (modal) {
      modal.remove();
    });
  }

  window.__internalCommentsCleanup = cleanup;
  if (!window.__internalCommentsVisitHookRegistered && window.swup?.hooks) {
    window.__internalCommentsVisitHookRegistered = true;
    window.swup.hooks.on("visit:start", function () {
      window.__internalCommentsCleanup?.();
    });
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char];
    });
  }

  function formatDate(value) {
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
  }

  function safeBadgeColor(value) {
    var color = String(value || "").trim();
    return /^(#[0-9a-f]{3,8}|[a-z]{1,32}|rgb\([0-9%,.\s]+\))$/i.test(color) ? color : "";
  }

  function icon(name, active) {
    var paths = {
      edit: 'M813.039 318.772L480.53 651.278H360.718V531.463L693.227 198.961C697.904 194.284 704.027 192 710.157 192C716.302 192 722.436 194.284 727.114 198.961L813.039 284.88C817.72 289.561 820 295.684 820 301.825C820 307.95 817.72 314.093 813.039 318.772ZM710.172 261.888L420.624 551.431V591.376H460.561L750.109 301.825L710.172 261.888ZM490.517 291.845H240.906V771.09H720.156V521.479C720.156 504.947 733.559 491.529 750.109 491.529C766.653 491.529 780.063 504.947 780.063 521.479V791.059C780.063 813.118 762.18 831 740.125 831H220.937C198.882 831 181 813.118 181 791.059V271.872C181 249.817 198.882 231.935 220.937 231.935H490.517C507.06 231.935 520.47 245.352 520.47 261.888C520.47 278.424 507.06 291.845 490.517 291.845Z',
      delete: 'm341.013 394.667 27.755 393.45h271.83l27.733-393.45h64.106l-28.01 397.952a64 64 0 0 1-63.83 59.498H368.768a64 64 0 0 1-63.83-59.52l-28.053-397.93h64.128zm139.307 19.818v298.667h-64V414.485h64zm117.013 0v298.667h-64V414.485h64zM181.333 288h640v64h-640v-64zm453.483-106.667v64h-256v-64h256z',
      reply: 'M810.667 213.333a64 64 0 0 1 64 64V704a64 64 0 0 1-64 64H478.336l-146.645 96.107a21.333 21.333 0 0 1-33.024-17.856V768h-85.334a64 64 0 0 1-64-64V277.333a64 64 0 0 1 64-64h597.334zm0 64H213.333V704h149.334v63.296L459.243 704h351.424V277.333zm-271.36 213.334v64h-176.64v-64h176.64zm122.026-128v64H362.667v-64h298.666z',
      like: 'M850.654 323.804c-11.042-25.625-26.862-48.532-46.885-68.225-20.022-19.61-43.258-34.936-69.213-45.73-26.78-11.124-55.124-16.727-84.375-16.727-40.622 0-80.256 11.123-114.698 32.135A214.79 214.79 0 0 0 512 241.819a214.79 214.79 0 0 0-23.483-16.562c-34.442-21.012-74.076-32.135-114.698-32.135-29.25 0-57.595 5.603-84.375 16.727-25.872 10.711-49.19 26.12-69.213 45.73-20.105 19.693-35.843 42.6-46.885 68.225-11.453 26.615-17.303 54.877-17.303 83.963 0 27.439 5.603 56.03 16.727 85.117 9.31 24.307 22.659 49.52 39.715 74.981 27.027 40.293 64.188 82.316 110.33 124.915 76.465 70.615 152.189 119.394 155.402 121.371l19.528 12.525c8.652 5.52 19.776 5.52 28.427 0l19.529-12.525c3.213-2.06 78.854-50.756 155.401-121.371 46.143-42.6 83.304-84.622 110.33-124.915 17.057-25.46 30.487-50.674 39.716-74.981 11.124-29.087 16.727-57.678 16.727-85.117.082-29.086-5.768-57.348-17.221-83.963zM512 761.5S218.665 573.55 218.665 407.767c0-83.963 69.461-152.023 155.154-152.023 60.233 0 112.473 33.618 138.181 82.727 25.708-49.109 77.948-82.727 138.18-82.727 85.694 0 155.155 68.06 155.155 152.023C805.335 573.551 512 761.5 512 761.5z',
      close: 'M697.173 85.333h-369.92c-144.64 0-241.92 101.547-241.92 252.587v348.587c0 150.613 97.28 252.16 241.92 252.16h369.92c144.64 0 241.494-101.547 241.494-252.16V337.92c0-151.04-96.854-252.587-241.494-252.587z',
      closeCross: 'm640.683 587.52-75.947-75.861 75.904-75.862a37.29 37.29 0 0 0 0-52.778 37.205 37.205 0 0 0-52.779 0l-75.946 75.818-75.862-75.946a37.419 37.419 0 0 0-52.821 0 37.419 37.419 0 0 0 0 52.821l75.947 75.947-75.776 75.733a37.29 37.29 0 1 0 52.778 52.821l75.776-75.776 75.947 75.947a37.376 37.376 0 0 0 52.779-52.821z',
      verified: 'm894.4 461.56-54.4-63.2c-10.4-12-18.8-34.4-18.8-50.4v-68c0-42.4-34.8-77.2-77.2-77.2h-68c-15.6 0-38.4-8.4-50.4-18.8l-63.2-54.4c-27.6-23.6-72.8-23.6-100.8 0l-62.8 54.8c-12 10-34.8 18.4-50.4 18.4h-69.2c-42.4 0-77.2 34.8-77.2 77.2v68.4c0 15.6-8.4 38-18.4 50l-54 63.6c-23.2 27.6-23.2 72.4 0 100l54 63.6c10 12 18.4 34.4 18.4 50v68.4c0 42.4 34.8 77.2 77.2 77.2h69.2c15.6 0 38.4 8.4 50.4 18.8l63.2 54.4c27.6 23.6 72.8 23.6 100.8 0l63.2-54.4c12-10.4 34.4-18.8 50.4-18.8h68c42.4 0 77.2-34.8 77.2-77.2v-68c0-15.6 8.4-38.4 18.8-50.4l54.4-63.2c23.2-27.6 23.2-73.2-.4-100.8zm-216-25.2-193.2 193.2a30 30 0 0 1-42.4 0l-96.8-96.8a30.16 30.16 0 0 1 0-42.4c11.6-11.6 30.8-11.6 42.4 0l75.6 75.6 172-172c11.6-11.6 30.8-11.6 42.4 0 11.6 11.6 11.6 30.8 0 42.4z'
    };
    if (name === "close") return '<svg class="wl-close-icon" viewBox="0 0 1024 1024" width="24" height="24" aria-hidden="true"><path d="' + paths.close + '" fill="currentColor"></path><path d="' + paths.closeCross + '" fill="#888"></path></svg>';
    if (name === "verified") return '<svg class="verified-icon" viewBox="0 0 1024 1024" width="14" height="14" aria-hidden="true"><path d="' + paths.verified + '" fill="#27ae60"></path></svg>';
    var path = paths[name];
    var isLiked = name === "like" && Boolean(active);
    // use Waline's filled path only after a like, so the idle state remains
    // the dark outline readers expect
    if (name === "like" && isLiked) path = path.split("M512 761.5")[0];
    var fill = name === "delete" || isLiked ? "red" : "currentColor";
    return '<svg viewBox="0 0 1024 1024" width="24" height="24" aria-hidden="true"><path d="' + path + '" fill="' + fill + '"></path></svg>';
  }

  function init(root) {
    if (!root || root.dataset.ready) return;
    root.dataset.ready = "true";
    root.dataset.authHandlerVersion = "delegated-v3";
    function message(name, fallback) {
      return root.dataset["msg" + name] || fallback;
    }
    var slug = root.dataset.commentsSlug;
    var editor = root.querySelector(".wl-editor");
    var form = root.querySelector(".wl-panel");
    var composer = root.querySelector(":scope > .wl-comment");
    var defaultPlaceholder = editor ? editor.getAttribute("placeholder") || "" : "";
    var replyTarget = null;
    var editTarget = null;
    var replyComposer = null;
    var editComposer = null;
    var gifSearchTimer = null;
    cleanupTasks.push(function () { if (gifSearchTimer) clearTimeout(gifSearchTimer); });
    var gifSearchSequence = 0;
    var previewControllers = new Set();
    cleanupTasks.push(function () {
      previewControllers.forEach(function (controller) { controller.abort(); });
      previewControllers.clear();
    });
    var comments = [];
    var sort = "latest";
    var assetsPromise = null;
    var imageInput = root.querySelector("[data-comment-image]");
    var preview = root.querySelector(".internal-comment-preview");
    var isAuthenticated = root.dataset.authenticated === "true";
    var commentRequiresLogin = root.dataset.commentRequireLogin === "true";
    var toastRegion = root.querySelector("[data-comment-toasts]");
    var authModal = root.querySelector("[data-auth-modal]") || document.querySelector("[data-auth-modal]");
    if (authModal) authModal.dataset.internalOwned = "true";
    if (authModal && authModal.parentNode !== document.body) document.body.appendChild(authModal);
    function openAuthModal(requestedPanel) {
      if (!authModal) return;
      requestedPanel = requestedPanel || "login";
      var requestedTab = authModal.querySelector('[data-auth-tab="' + requestedPanel + '"]');
      if (!requestedTab) requestedPanel = "login";
      requestedTab = authModal.querySelector('[data-auth-tab="' + requestedPanel + '"]');
      if (requestedTab) requestedTab.click();
      authModal.hidden = false;
      var first = authModal.querySelector('[data-auth-panel="' + requestedPanel + '"] input');
      if (first) setTimeout(function () { first.focus(); }, 0);
    }
    function showToast(text, kind) {
      if (!toastRegion || !text) return;
      var existing = Array.from(toastRegion.querySelectorAll(".internal-comment-toast")).find(function (item) {
        return item.dataset.message === text;
      });
      if (existing) {
        existing.classList.remove("is-leaving");
        return;
      }
      toastRegion.replaceChildren();
      var toast = document.createElement("div");
      toast.className = "internal-comment-toast is-" + (kind || "error");
      toast.dataset.message = text;
      toast.setAttribute("role", kind === "error" ? "alert" : "status");
      var iconNode = document.createElement("i");
      iconNode.className = "fa-solid " + (kind === "success" ? "fa-circle-check" : "fa-circle-exclamation");
      iconNode.setAttribute("aria-hidden", "true");
      var content = document.createElement("span");
      content.textContent = text;
      var close = document.createElement("button");
      close.type = "button";
      close.className = "internal-comment-toast-close";
      close.setAttribute("aria-label", message("Cancel", "Close"));
      close.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i>';
      close.addEventListener("click", function () { toast.remove(); });
      toast.append(iconNode, content, close);
      toastRegion.appendChild(toast);
      setTimeout(function () { toast.classList.add("is-leaving"); setTimeout(function () { toast.remove(); }, 180); }, 4200);
    }
    var confirmModal = root.querySelector("[data-comment-confirm]") || document.querySelector("[data-comment-confirm]");
    var confirmResolver = null;
    if (confirmModal) {
      confirmModal.dataset.internalOwned = "true";
      if (confirmModal.parentNode !== document.body) document.body.appendChild(confirmModal);
    }
    function closeConfirmation(result) {
      if (!confirmModal || confirmModal.hidden) return;
      confirmModal.hidden = true;
      var resolver = confirmResolver;
      confirmResolver = null;
      if (resolver) resolver(Boolean(result));
    }
    function requestConfirmation(text) {
      if (!confirmModal) return Promise.resolve(false);
      var label = confirmModal.querySelector("[data-confirm-message]");
      if (label) label.textContent = text;
      if (confirmResolver) confirmResolver(false);
      confirmModal.hidden = false;
      var accept = confirmModal.querySelector("[data-confirm-accept]");
      if (accept) setTimeout(function () { accept.focus(); }, 0);
      return new Promise(function (resolve) { confirmResolver = resolve; });
    }
    // Delegate from the stable comments root. Swup and comment redraws may
    // replace individual links, but the composer should still open its modal.
    root.addEventListener("click", function (event) {
      var opener = event.target.closest(".internal-auth-open");
      if (!opener || !root.contains(opener) || !authModal) return;
      event.preventDefault();
      var requestedPanel = opener.dataset.authOpenPanel;
      setTimeout(function () { openAuthModal(requestedPanel); }, 0);
    }, true);
    var authClose = (authModal && authModal.querySelector("[data-auth-close]")) || root.querySelector("[data-auth-close]");
    if (authClose && authModal) authClose.addEventListener("click", function () { authModal.hidden = true; });
    if (authModal) {
      authModal.addEventListener("click", function (event) { if (event.target === authModal) authModal.hidden = true; });
      document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        if (confirmModal && !confirmModal.hidden) closeConfirmation(false);
        else if (!authModal.hidden) authModal.hidden = true;
      }, { signal: lifecycleSignal });
      authModal.querySelectorAll("[data-auth-tab]").forEach(function (tab) { tab.addEventListener("click", function () {
        var panel = tab.dataset.authTab;
        authModal.querySelectorAll("[data-auth-tab]").forEach(function (item) { var active = item === tab; item.classList.toggle("is-active", active); item.setAttribute("aria-selected", active ? "true" : "false"); });
        authModal.querySelectorAll("[data-auth-panel]").forEach(function (form) { form.hidden = form.dataset.authPanel !== panel; });
        var heading = authModal.querySelector("[data-auth-heading-title]");
        var headingIcon = authModal.querySelector("[data-auth-heading-icon]");
        if (heading) heading.textContent = tab.dataset.authLabel || tab.textContent.trim();
        if (headingIcon) {
          headingIcon.classList.remove("fa-right-to-bracket", "fa-user-plus");
          headingIcon.classList.add(tab.dataset.authIcon || "fa-right-to-bracket");
        }
      }); });
    }
    if (confirmModal) {
      confirmModal.querySelectorAll("[data-confirm-cancel]").forEach(function (button) { button.addEventListener("click", function () { closeConfirmation(false); }); });
      var confirmAccept = confirmModal.querySelector("[data-confirm-accept]");
      if (confirmAccept) confirmAccept.addEventListener("click", function () { closeConfirmation(true); });
    }
    var authForms = authModal ? authModal.querySelectorAll("[data-auth-form]") : [];
    authForms.forEach(function (authForm) { authForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var errorBox = authForm.querySelector(".internal-auth-error");
      if (errorBox) errorBox.textContent = "";
      var data = new FormData(authForm);
      var isRegister = authForm.dataset.authPanel === "register";
      var endpoint = isRegister ? "/api/comments/register/" : "/api/comments/login/";
      var submitButton = authForm.querySelector("button[type=submit]");
      var originalButtonHtml = submitButton ? submitButton.innerHTML : "";
      if (submitButton) {
        submitButton.disabled = true;
        if (isRegister) {
          submitButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i><span>' +
            escapeHtml(message("SendingVerification", "Sending verification email…")) + '</span>';
        }
      }
      fetch(endpoint, { method: "POST", body: data, headers: { "X-CSRFToken": csrf(), Accept: "application/json" }, credentials: "same-origin" })
        .then(function (response) { return response.json().catch(function () { return {}; }).then(function (body) { if (!response.ok) throw new Error(body.error || (isRegister ? message("UnableRegister", "Unable to register.") : message("UnableSignIn", "Unable to sign in."))); return body; }); })
        .then(function (body) {
          if (isRegister && body.pending) {
            if (errorBox) { errorBox.className = "internal-auth-success"; errorBox.textContent = message("VerificationSent", "Verification email sent. Please check your inbox before signing in."); }
            authForm.reset();
            return;
          }
          authModal.hidden = true;
          window.location.reload();
        })
        .catch(function (error) { if (errorBox) errorBox.textContent = error.message; })
        .finally(function () {
          if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonHtml;
          }
        });
    }); });

    function csrf() {
      var token = (form && form.querySelector("input[name=csrfmiddlewaretoken]")) || root.querySelector("input[name=csrfmiddlewaretoken]") || (authModal && authModal.querySelector("input[name=csrfmiddlewaretoken]"));
      return token ? token.value : "";
    }
    function extractFencedCodeBlocks(value) {
      var blocks = [];
      var output = [];
      var lines = String(value || "").replace(/\r\n?/g, "\n").split("\n");
      for (var index = 0; index < lines.length; index += 1) {
        var opening = /^ {0,3}(`{3,}|~{3,})[ \t]*(.*)$/.exec(lines[index]);
        if (!opening) {
          output.push(lines[index]);
          continue;
        }

        var closing = new RegExp("^ {0,3}" + opening[1].charAt(0) + "{" + opening[1].length + ",}[ \\t]*$");
        var end = index + 1;
        while (end < lines.length && !closing.test(lines[end])) end += 1;
        if (end >= lines.length) {
          output.push(lines[index]);
          continue;
        }

        var info = opening[2].trim().replace(/^\{\.?|\}$/g, "");
        var language = (info.split(/\s+/, 1)[0] || "text").replace(/^\./, "").toLowerCase();
        if (!/^[\w+-]+$/.test(language)) language = "text";
        var marker = "COMMENTCODEBLOCKPLACEHOLDER" + blocks.length + "TOKEN";
        blocks.push('<pre><code class="hljs language-' + language + '">' + escapeHtml(lines.slice(index + 1, end).join("\n")) + "</code></pre>");
        output.push(marker);
        index = end;
      }
      return { source: output.join("\n"), blocks: blocks };
    }

    function renderLocalPreview(value) {
      var parsed = extractFencedCodeBlocks(value);
      var html = escapeHtml(parsed.source)
        .replace(/&lt;font(?:\s+color=(?:&quot;|&#039;)?([#a-z0-9(),.%\s]+)(?:&quot;|&#039;)?)?&gt;([\s\S]*?)&lt;\/font&gt;/gi, function (_, color, content) { return '<font' + (color ? ' color="' + color.trim() + '"' : '') + '>' + content + '</font>'; })
        .replace(/&lt;img\b[^>]*?src=(?:&quot;|&#039;)(https?:\/\/[^&]+?)(?:&quot;|&#039;)[^>]*?&gt;/gi, function (_, src) { return '<img class="internal-preview-image" src="' + src + '" alt="">'; })
        .replace(/!\[([^\]]*)\]\(((?:https?:\/\/|\/)[^\s)]+)\)/g, '<img class="internal-preview-image" alt="$1" src="$2">')
        .replace(/\[([^\]]+)\]\(((?:https?:\/\/|\/)[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="nofollow noopener noreferrer">$1</a>')
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/__(.+?)__/g, "<strong>$1</strong>")
        .replace(/\*(?!\s)(.+?)(?<!\s)\*/g, "<em>$1</em>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\n/g, "<br>");
      return html.replace(/COMMENTCODEBLOCKPLACEHOLDER(\d+)TOKEN/g, function (_, blockIndex) {
        return parsed.blocks[Number(blockIndex)] || "";
      });
    }

    function renderPreviewFor(node) {
      if (!node) return;
      var input = node.querySelector(".wl-editor");
      var pane = node.querySelector(".internal-comment-preview");
      var content = pane && pane.querySelector(".wl-content");
      if (!input || !content) return;
      var source = input.value;
      content.innerHTML = renderLocalPreview(source);

      if (node._commentPreviewTimer) clearTimeout(node._commentPreviewTimer);
      if (node._commentPreviewController) node._commentPreviewController.abort();
      node._commentPreviewTimer = setTimeout(function () {
        var controller = new AbortController();
        node._commentPreviewController = controller;
        previewControllers.add(controller);
        var data = new FormData();
        data.append("content", source);
        fetch("/api/comments/preview/", {
          method: "POST",
          body: data,
          headers: { "X-CSRFToken": csrf(), Accept: "application/json" },
          credentials: "same-origin",
          signal: controller.signal
        })
          .then(function (response) { if (!response.ok) throw new Error(message("PreviewUnavailable", "Preview unavailable")); return response.json(); })
          .then(function (body) {
            if (input.value === source && body.ok && typeof body.html === "string") content.innerHTML = body.html;
          })
          .catch(function () { /* keep the local preview when the request is unavailable */ })
          .finally(function () { previewControllers.delete(controller); });
      }, 180);
    }
    function bindComposer(node, mode, item) {
      if (!node) return node;
      node.dataset.composerMode = mode || "create";
      var input = node.querySelector(".wl-editor");
      var pane = node.querySelector(".internal-comment-preview");
      var parent = node.querySelector('input[name="parent_id"]');
      if (mode === "reply" && item) {
        if (parent) parent.value = item.id;
        if (input) input.placeholder = "@" + (item.author || "");
      } else if (mode === "edit" && item) {
        node.dataset.editId = item.id;
        if (input) { input.value = item.content || ""; input.placeholder = message("EditPlaceholder", "Edit your comment"); }
      }
      var file = node.querySelector("[data-comment-image]");
      if (file) {
        var id = "wl-image-upload-" + Math.random().toString(36).slice(2);
        file.id = id;
        var label = node.querySelector('label[data-comment-action="image"]');
        if (label) label.setAttribute("for", id);
      }
      if (input) input.addEventListener("input", function () {
        var counter = node.querySelector(".internal-comment-count");
        if (counter) counter.textContent = input.value.length + " / 5000";
        if (pane && !pane.hidden) renderPreviewFor(node);
      });
      return node;
    }
    function cloneComposer(mode, item) {
      if (!composer) return null;
      var clone = composer.cloneNode(true);
      clone.classList.add("internal-inline-composer");
      clone.removeAttribute("id");
      var mainInputs = composer.querySelectorAll("input[name=nickname], input[name=email], input[name=website]");
      mainInputs.forEach(function (source) {
        var target = clone.querySelector('[name="' + source.name + '"]');
        if (target) target.value = source.value;
      });
      var input = clone.querySelector(".wl-editor");
      if (input) input.value = mode === "edit" && item ? item.content || "" : "";
      var pane = clone.querySelector(".internal-comment-preview");
      if (pane) {
        // reset preview per composer, so reply and edit boxes never inherit the main editor state
        pane.hidden = true;
        var previewButton = clone.querySelector('[data-comment-action="preview"]');
        if (previewButton) previewButton.classList.remove("active");
      }
      var panel = clone.querySelector(".wl-panel");
      if (panel && (mode === "reply" || mode === "edit")) {
        panel.insertAdjacentHTML("beforeend", '<button type="button" class="wl-close" data-composer-cancel title="' + escapeHtml(message("Cancel", "Cancel")) + '">' + icon("close") + '</button>');
      }
      return bindComposer(clone, mode, item);
    }
    function clearReplyTarget(redraw) {
      replyTarget = null;
      if (replyComposer) { replyComposer.remove(); replyComposer = null; }
      if (redraw) draw();
    }
    function clearEditTarget(redraw) {
      editTarget = null;
      if (editComposer) { editComposer.remove(); editComposer = null; }
      if (redraw) draw();
    }
    function mountComposer(list) {
      if (replyTarget) {
        var targetId = String(replyTarget.id).replace(/"/g, "&quot;");
        var wrapper = list.querySelector('[data-reply-wrapper="' + targetId + '"]');
        if (wrapper) {
          if (!replyComposer) replyComposer = cloneComposer("reply", replyTarget.item);
          if (replyComposer && !replyComposer.parentNode) wrapper.appendChild(replyComposer);
        } else { replyTarget = null; replyComposer = null; }
      }
      if (editTarget) {
        var editId = String(editTarget.id).replace(/"/g, "&quot;");
        var editWrapper = list.querySelector('[data-edit-wrapper="' + editId + '"]');
        if (editWrapper) {
          if (!editComposer) editComposer = cloneComposer("edit", editTarget.item);
          if (editComposer && !editComposer.parentNode) editWrapper.appendChild(editComposer);
        } else { editTarget = null; editComposer = null; }
      }
    }
    function externalUrl(value) {
      var url = String(value || "").trim();
      return /^(https?:\/\/)/i.test(url) ? url : "";
    }
    function draw() {
      var list = root.querySelector("[data-comments-items]");
      var visible = comments.slice().sort(function (a, b) {
        if (Boolean(a.is_sticky) !== Boolean(b.is_sticky)) return Number(b.is_sticky) - Number(a.is_sticky);
        if (sort === "oldest") return new Date(a.created_at) - new Date(b.created_at);
        if (sort === "likes") return b.like_count - a.like_count;
        return new Date(b.created_at) - new Date(a.created_at);
      });
      root.querySelector("[data-comment-count]").textContent = comments.length;
      if (!visible.length) { list.innerHTML = '<div class="wl-empty">' + escapeHtml(message("NoComments", "No comments yet.")) + '</div>'; mountComposer(list); return; }
      var groups = {};
      visible.forEach(function (item) { (groups[item.parent_id || "root"] ||= []).push(item); });
      function card(item, isReply, nestedReplies) {
          var avatarImage = item.avatar ? '<img class="wl-user-avatar" src="' + escapeHtml(item.avatar) + '" alt="">' : '<span class="internal-avatar-fallback">' + escapeHtml(String(item.author || "").slice(0, 1).toUpperCase()) + '</span>';
          var avatar = '<div class="wl-user" aria-hidden="true">' + avatarImage + (item.verified ? icon("verified") : "") + '</div>';
          var meta = [["addr", item.ip_address], ["browser", item.browser], ["os", item.operating_system]]
            .filter(function (entry) { return Boolean(entry[1]); })
            .map(function (entry) { var value = escapeHtml(entry[1]); return '<span class="wl-' + entry[0] + '" data-value="' + value + '">' + value + '</span>'; })
            .join('');
          var ownerActions = item.can_edit ? '<button type="button" class="wl-edit" data-edit="' + item.id + '" title="' + escapeHtml(message("Edit", "Edit")) + '">' + icon("edit") + '</button>' : '';
          var deleteAction = item.can_delete ? '<button type="button" class="wl-delete" data-delete="' + item.id + '" title="' + escapeHtml(message("Delete", "Delete")) + '">' + icon("delete") + '</button>' : '';
          var isReplyTarget = replyTarget && String(replyTarget.id) === String(item.id);
          var replyWrapper = isReplyTarget ? '<div class="wl-reply-wrapper" data-reply-wrapper="' + escapeHtml(item.id) + '"></div>' : '';
          var isEditTarget = editTarget && String(editTarget.id) === String(item.id);
          var editWrapper = isEditTarget ? '<div class="wl-edit-wrapper" data-edit-wrapper="' + escapeHtml(item.id) + '"></div>' : '';
          var replyTitle = isReplyTarget ? message("CancelReply", "Cancel reply") : message("Reply", "Reply");
          var replyNeedsAuth = !isAuthenticated && commentRequiresLogin;
          var replyClass = (isReplyTarget ? "wl-reply active" : "wl-reply") + (replyNeedsAuth ? " internal-auth-open" : "");
          var replyAuthAttributes = replyNeedsAuth ? ' data-auth-open-panel="login"' : '';
          var website = externalUrl(item.website);
          var nickname = website ? '<a class="wl-nick" href="' + escapeHtml(website) + '" target="_blank" rel="nofollow noopener noreferrer">' + escapeHtml(item.author) + '</a>' : '<span class="wl-nick">' + escapeHtml(item.author) + '</span>';
          var badges = '';
          (item.badges || []).forEach(function (badge) { var color = safeBadgeColor(badge.color); badges += '<span class="wl-badge"' + (color ? ' style="color:' + color + ';border-color:' + color + '"' : '') + '>' + escapeHtml(badge.name) + '</span>'; });
          if (item.is_sticky) badges += '<span class="wl-badge">' + escapeHtml(message("Pinned", "Pinned")) + '</span>';
          var content = item.content_html || escapeHtml(item.content).replace(/\n/g, "<br>");
          if (isReply && item.parent_id) {
            var parent = comments.find(function (candidate) { return String(candidate.id) === String(item.parent_id); });
            if (parent) {
              var mention = '<a href="#comment-' + item.parent_id + '" class="internal-reply-mention">@' + escapeHtml(parent.author) + '</a>: ';
              if (/^<p(?:\s[^>]*)?>/i.test(content)) content = content.replace(/^<p(?:\s[^>]*)?>/i, function (tag) { return tag + mention; });
              else content = '<p>' + mention + content + '</p>';
            }
          }
          var adminActions = item.can_moderate && !isReply ? '<div class="wl-admin-actions"><button type="button" class="wl-btn wl-sticky" data-sticky="' + item.id + '">' + escapeHtml(item.is_sticky ? message("Unpin", "Unpin") : message("Pin", "Pin")) + '</button></div>' : '';
          var nestedMarkup = nestedReplies ? '<div class="wl-quote internal-reply-quote">' + nestedReplies + '</div>' : '';
          var body = isEditTarget ? editWrapper : '<div class="wl-content">' + content + '</div>';
          var likeTitle = item.liked ? message("Unlike", "Unlike") : message("Like", "Like");
          var likeClass = "wl-like" + (!isAuthenticated ? " internal-auth-open" : "");
          var likeAuthAttributes = !isAuthenticated ? ' data-auth-open-panel="login"' : '';
          return '<div class="wl-card-item' + (isReply ? ' internal-reply-card-item' : '') + '" id="comment-' + item.id + '">' + avatar + '<div class="wl-card"><div class="wl-head">' + nickname + badges + '<span class="wl-time">' + formatDate(item.created_at) + '</span><div class="wl-comment-actions">' + ownerActions + deleteAction + '<button type="button" class="' + likeClass + '" data-like="' + item.id + '"' + likeAuthAttributes + ' title="' + likeTitle + '">' + icon("like", item.liked) + '<span>' + item.like_count + '</span></button><button type="button" class="' + replyClass + '" data-reply="' + item.id + '"' + replyAuthAttributes + ' title="' + replyTitle + '">' + icon("reply") + '</button></div></div><div class="wl-meta" aria-hidden="true">' + meta + '</div>' + body + adminActions + replyWrapper + nestedMarkup + '</div></div>';
      }
      function descendants(parentId, output) {
        (groups[parentId] || []).forEach(function (child) {
          output.push(child);
          descendants(child.id, output);
        });
      }
      list.innerHTML = (groups.root || []).map(function (item) {
        var replies = [];
        descendants(item.id, replies);
        return card(item, false, replies.length ? replies.map(function (reply) { return card(reply, true); }).join("") : "");
      }).join("");
      mountComposer(list);
    }
    function load() {
      fetch("/api/comments/" + encodeURIComponent(slug) + "/", { headers: { Accept: "application/json" } })
        .then(function (response) { return response.json(); })
        .then(function (data) { comments = data.comments || []; draw(); })
        .catch(function () { root.querySelector("[data-comments-items]").innerHTML = '<div class="wl-empty">' + escapeHtml(message("UnableLoadComments", "Unable to load comments.")) + '</div>'; });
    }
    function parseJsonResponse(response, fallbackMessage) {
      return response.text().then(function (text) {
        var body = {};
        try { body = text ? JSON.parse(text) : {}; } catch (error) { throw new Error(fallbackMessage + " (HTTP " + response.status + ")."); }
        if (!response.ok) throw new Error(body.error || (fallbackMessage + " (HTTP " + response.status + ")."));
        return body;
      });
    }
    function loadAssets() {
      if (!assetsPromise) {
        assetsPromise = fetch("/api/comment-assets/", { headers: { Accept: "application/json" }, credentials: "same-origin" })
          .then(function (response) { return parseJsonResponse(response, message("UnableLoadAssets", "Unable to load comment assets")); });
      }
      return assetsPromise;
    }
    function insertAtCursor(input, value) {
      if (!input) return;
      var start = input.selectionStart == null ? input.value.length : input.selectionStart;
      var end = input.selectionEnd == null ? input.value.length : input.selectionEnd;
      input.value = input.value.slice(0, start) + value + input.value.slice(end);
      input.selectionStart = input.selectionEnd = start + value.length;
      input.dispatchEvent(new Event("input"));
      input.focus();
    }
    function closePicker(node, immediate) {
      var picker = node && node.querySelector(".internal-comment-picker");
      if (!picker) return;
      picker.classList.remove("display");
      node.querySelectorAll("[data-comment-action=emoji], [data-comment-action=gif]").forEach(function (button) { button.classList.remove("active"); });
      if (immediate) picker.hidden = true;
      else setTimeout(function () { if (!picker.classList.contains("display")) picker.hidden = true; }, 220);
    }
    function showEmojiPicker(node, packs, selectedIndex) {
      var picker = node.querySelector(".internal-comment-picker");
      if (!picker) return;
      packs = Array.isArray(packs) ? packs : [];
      var index = Number.isInteger(selectedIndex) ? selectedIndex : parseInt(picker.dataset.emojiPackIndex || "0", 10);
      if (!Number.isFinite(index)) index = 0;
      if (index < 0 || index >= packs.length) index = 0;
      var wasOpen = picker.classList.contains("display");
      picker.className = "wl-emoji-popup internal-comment-picker";
      picker.innerHTML = "";
      picker.hidden = false;
      picker.dataset.pickerMode = "emoji";
      picker.dataset.emojiPackIndex = String(index);
      picker._emojiPacks = packs;
      var activePack = packs[index] || { items: [] };
      var tabWrapper = document.createElement("div");
      tabWrapper.className = "wl-tab-wrapper";
      picker.appendChild(tabWrapper);
      var added = 0;
      (activePack.items || []).forEach(function (item) {
          var button = document.createElement("button");
          button.type = "button";
          button.title = item.name || "emoji";
          var token = ":" + (item.name || "") + ":";
          button.dataset.insert = token;
          button.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            insertAtCursor(node.querySelector(".wl-editor"), token);
          });
          var image = document.createElement("img");
          image.className = "wl-emoji";
          image.src = item.url || "";
          image.alt = item.name || "";
          image.loading = "lazy";
          image.referrerPolicy = "no-referrer";
          button.appendChild(image);
          tabWrapper.appendChild(button);
          added += 1;
      });
      if (!added) {
        var hint = document.createElement("span");
        hint.className = "internal-picker-empty";
        hint.textContent = message("NoEmoji", "No emoji yet. Add a Comment emoji name and image URL in the admin.");
        tabWrapper.appendChild(hint);
      }
      if (packs.length > 1) {
        var tabs = document.createElement("div");
        tabs.className = "wl-tabs";
        packs.forEach(function (pack, packIndex) {
          var tabButton = document.createElement("button");
          tabButton.type = "button";
          tabButton.className = "wl-tab" + (packIndex === index ? " active" : "");
          tabButton.dataset.emojiPackIndex = String(packIndex);
          tabButton.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            showEmojiPicker(node, packs, packIndex);
            var emojiAction = node.querySelector('[data-comment-action="emoji"]');
            if (emojiAction) emojiAction.classList.add("active");
          });
          var tabImage = document.createElement("img");
          tabImage.className = "wl-emoji";
          var firstItem = (pack.items || [])[0] || {};
          tabImage.src = pack.icon || firstItem.url || "";
          tabImage.alt = pack.name || "";
          tabImage.loading = "lazy";
          tabImage.referrerPolicy = "no-referrer";
          tabButton.appendChild(tabImage);
          tabs.appendChild(tabButton);
        });
        picker.appendChild(tabs);
      }
      if (wasOpen) picker.classList.add("display");
      else (window.requestAnimationFrame || function (callback) { setTimeout(callback, 0); })(function () { picker.classList.add("display"); });
    }
    function showGifPicker(node, sources) {
      var picker = node.querySelector(".internal-comment-picker");
      if (!picker) return;
      picker.className = "wl-gif-popup internal-comment-picker";
      picker.innerHTML = "";
      var search = document.createElement("input");
      search.type = "search";
      search.placeholder = message("SearchGif", "Search GIF");
      search.className = "internal-gif-search";
      picker.appendChild(search);
      var results = document.createElement("div");
      results.className = "internal-gif-results";
      picker.appendChild(results);
      function query() {
        gifSearchSequence += 1;
        var sequence = gifSearchSequence;
        var term = search.value.trim();
        if (!term) {
          results.textContent = message("EnterGifKeyword", "Enter a keyword to search GIFs");
          return;
        }
        results.textContent = message("Loading", "Loading…");
        var requests = (sources || []).map(function (source) {
          var endpoint = String(source.endpoint || "");
          if (!endpoint) return Promise.resolve([]);
          var separator = endpoint.indexOf("?") >= 0 ? "&" : "?";
          return fetch(endpoint + separator + "q=" + encodeURIComponent(term), { headers: { Accept: "application/json" } })
            .then(function (response) { return response.ok ? response.text() : ""; })
            .then(function (text) { try { var body = text ? JSON.parse(text) : []; return body.results || body.data || body.gifs || body; } catch (error) { return []; } })
            .catch(function () { return []; });
        });
        Promise.all(requests).then(function (groups) {
          if (sequence !== gifSearchSequence) return;
          results.innerHTML = "";
          var items = [].concat.apply([], groups);
          if (!items.length) { results.textContent = message("NoGifs", "No GIFs found"); return; }
          items.slice(0, 40).forEach(function (item) {
            var url = typeof item === "string" ? item : ((item.images && ((item.images.fixed_width_small && item.images.fixed_width_small.url) || (item.images.fixed_width && item.images.fixed_width.url) || (item.images.original && item.images.original.url))) || (item.media_formats && ((item.media_formats.gif && item.media_formats.gif.url) || (item.media_formats.mediumgif && item.media_formats.mediumgif.url))) || item.src || item.image || item.media || item.url || "");
            if (!/^https?:\/\//i.test(url)) return;
            var button = document.createElement("button");
            button.type = "button";
            var gifMarkdown = "![gif](" + url + ")";
            button.dataset.insert = gifMarkdown;
            // bind each asynchronous GIF result as it is created, so insertion
            // does not depend on the root toolbar's delegated handler
            button.addEventListener("click", function (event) {
              event.preventDefault();
              event.stopPropagation();
              insertAtCursor(node.querySelector(".wl-editor"), gifMarkdown);
            });
            var image = document.createElement("img");
            image.src = url;
            image.alt = "GIF";
            image.loading = "lazy";
            button.appendChild(image);
            results.appendChild(button);
          });
        });
      }
      search.addEventListener("input", function () {
        if (gifSearchTimer) clearTimeout(gifSearchTimer);
        gifSearchTimer = setTimeout(query, 250);
      });
      picker.hidden = false;
      picker.dataset.pickerMode = "gif";
      delete picker._emojiPacks;
      (window.requestAnimationFrame || function (callback) { setTimeout(callback, 0); })(function () { picker.classList.add("display"); });
      query();
    }
    function submitComposer(node, submit) {
      var panel = node && node.querySelector(".wl-panel");
      if (!panel || !submit || submit.disabled || node.dataset.submitting === "true") return;
      var contentInput = panel.querySelector('.wl-editor[name="content"], .wl-editor');
      var content = contentInput ? contentInput.value.trim() : "";
      if (!content || content.length > 5000) {
        showToast(message("CommentLength", "Comment length must be between 1 and 5000 characters."), "error");
        if (contentInput) contentInput.focus();
        return;
      }
      node.dataset.submitting = "true";
      var data = new FormData();
      panel.querySelectorAll("input, textarea").forEach(function (input) { if (input.name) data.append(input.name, input.value); });
      submit.disabled = true;
      var editId = node.dataset.editId;
      var endpoint = editId ? "/api/comments/" + editId + "/edit/" : "/api/comments/" + encodeURIComponent(slug) + "/create/";
      fetch(endpoint, { method: "POST", body: data, headers: { "X-CSRFToken": csrf(), Accept: "application/json" }, credentials: "same-origin" })
        .then(function (response) { return parseJsonResponse(response, message("UnableSubmit", "Unable to submit comment")); })
        .then(function () {
          if (node === composer) { var mainEditor = node.querySelector(".wl-editor"); if (mainEditor) { mainEditor.value = ""; mainEditor.dispatchEvent(new Event("input")); } }
          if (node === replyComposer) { replyComposer.remove(); replyComposer = null; replyTarget = null; }
          if (node === editComposer) { editComposer.remove(); editComposer = null; editTarget = null; }
          draw(); load();
        })
        .catch(function (error) { showToast(error.message, "error"); })
        .finally(function () { submit.disabled = false; delete node.dataset.submitting; });
    }
    root.addEventListener("click", function (event) {
      var submitButton = event.target.closest(".internal-comment-submit");
      if (submitButton) { event.preventDefault(); submitComposer(submitButton.closest(".wl-comment"), submitButton); return; }
      var action = event.target.closest("[data-comment-action]");
      // limit actions to direct toolbar controls, so popup tabs and emoji items
      // cannot retrigger the button that opened them
      if (action && !action.closest(".wl-actions")) action = null;
      // preserve the guide link's native navigation, so it opens documentation instead of editing text
      if (action && action.dataset.commentAction !== "markdown") event.preventDefault();
      var actionComposer = action && action.closest(".wl-comment");
      if (action && (action.dataset.commentAction === "emoji" || action.dataset.commentAction === "gif") && actionComposer) {
        var picker = actionComposer.querySelector(".internal-comment-picker");
        if (picker && !picker.hidden && picker.dataset.pickerMode === action.dataset.commentAction) {
          closePicker(actionComposer);
          action.classList.remove("active");
          return;
        }
        if (picker) closePicker(actionComposer, true);
        actionComposer.querySelectorAll("[data-comment-action=emoji], [data-comment-action=gif]").forEach(function (button) { button.classList.remove("active"); });
        loadAssets().then(function (assets) {
          if (action.dataset.commentAction === "emoji") showEmojiPicker(actionComposer, assets.emoji, 0);
          else showGifPicker(actionComposer, assets.gif);
          action.classList.add("active");
        }).catch(function (error) { showToast(error.message, "error"); });
        return;
      }
      if (!action && !event.target.closest(".internal-comment-picker")) {
        root.querySelectorAll(".wl-comment").forEach(function (node) { closePicker(node); });
      }
      var emojiTab = event.target.closest("[data-emoji-pack-index]");
      if (emojiTab) {
        event.stopPropagation();
        var tabOwner = emojiTab.closest(".wl-comment");
        var tabPicker = tabOwner && tabOwner.querySelector(".internal-comment-picker");
        if (tabPicker && tabPicker._emojiPacks) {
          showEmojiPicker(tabOwner, tabPicker._emojiPacks, parseInt(emojiTab.dataset.emojiPackIndex || "0", 10));
          var emojiAction = tabOwner.querySelector('[data-comment-action="emoji"]');
          if (emojiAction) emojiAction.classList.add("active");
        }
        return;
      }
      var insertButton = event.target.closest("[data-insert]");
      if (insertButton) {
        event.stopPropagation();
        var insertOwner = insertButton.closest(".wl-comment");
        insertAtCursor(insertOwner && insertOwner.querySelector(".wl-editor"), insertButton.dataset.insert || "");
        return;
      }
      if (action && action.dataset.commentAction === "image") { var actionInput = actionComposer && actionComposer.querySelector("[data-comment-image]"); if (actionInput) actionInput.click(); return; }
      if (action && action.dataset.commentAction === "preview" && actionComposer) {
        var actionPreview = actionComposer.querySelector(".internal-comment-preview");
        if (!actionPreview) return;
        actionPreview.hidden = !actionPreview.hidden;
        action.classList.toggle("active", !actionPreview.hidden);
        if (!actionPreview.hidden) renderPreviewFor(actionComposer);
        return;
      }
      var sortButton = event.target.closest("[data-sort]");
      if (sortButton) { sort = sortButton.dataset.sort; root.querySelectorAll("[data-sort]").forEach(function (node) { node.classList.toggle("active", node === sortButton); }); draw(); return; }
      var replyButton = event.target.closest("[data-reply]");
      if (replyButton) {
        if (!isAuthenticated && commentRequiresLogin) {
          openAuthModal("login");
          return;
        }
        var replyId = String(replyButton.dataset.reply);
        if (replyTarget && replyTarget.id === replyId) {
          clearReplyTarget(true);
        } else {
          var replyItem = comments.find(function (item) { return String(item.id) === replyId; });
          if (replyItem) {
            clearReplyTarget(false);
            clearEditTarget(false);
            replyTarget = { id: replyId, author: String(replyItem.author || ""), item: replyItem };
            draw();
          }
        }
        if (replyComposer) { var replyEditor = replyComposer.querySelector(".wl-editor"); if (replyEditor) replyEditor.focus(); }
        return;
      }
      var composerCancel = event.target.closest("[data-composer-cancel]");
      if (composerCancel) {
        var cancelComposer = composerCancel.closest(".wl-comment");
        if (cancelComposer && cancelComposer.dataset.composerMode === "edit") clearEditTarget(true);
        else clearReplyTarget(true);
        return;
      }
      var stickyButton = event.target.closest("[data-sticky]");
      if (stickyButton) {
        fetch("/api/comments/" + stickyButton.dataset.sticky + "/sticky/", { method: "POST", headers: { "X-CSRFToken": csrf(), Accept: "application/json" }, credentials: "same-origin" })
          .then(function (response) { return parseJsonResponse(response, message("UnableUpdatePin", "Unable to update pin status.")); })
          .then(function () { load(); })
          .catch(function (error) { showToast(error.message, "error"); });
        return;
      }
      var editButton = event.target.closest("[data-edit]");
      if (editButton) {
        var editItem = comments.find(function (item) { return String(item.id) === String(editButton.dataset.edit); });
        if (editItem) {
          clearReplyTarget(false);
          clearEditTarget(false);
          editTarget = { id: String(editItem.id), item: editItem };
          draw();
          if (editComposer) { var editEditor = editComposer.querySelector(".wl-editor"); if (editEditor) editEditor.focus(); }
        }
        return;
      }
      var deleteButton = event.target.closest("[data-delete]");
      if (deleteButton) {
        requestConfirmation(message("DeleteConfirm", "Delete this comment?")).then(function (confirmed) {
          if (!confirmed) return;
          fetch("/api/comments/" + deleteButton.dataset.delete + "/delete/", { method: "POST", headers: { "X-CSRFToken": csrf(), Accept: "application/json" }, credentials: "same-origin" })
            .then(function (response) { return parseJsonResponse(response, message("UnableDelete", "Unable to delete comment.")); })
            .then(load)
            .catch(function (error) { showToast(error.message, "error"); });
        });
        return;
      }
      var likeButton = event.target.closest("[data-like]");
      if (likeButton && !likeButton.disabled) {
        if (!isAuthenticated) {
          openAuthModal("login");
          return;
        }
        likeButton.disabled = true;
        fetch("/api/comments/" + likeButton.dataset.like + "/like/", { method: "POST", headers: { "X-CSRFToken": csrf(), Accept: "application/json" }, credentials: "same-origin" })
          .then(function (response) { return parseJsonResponse(response, message("SignInLike", "Please sign in to like comments.")); })
          .then(load)
          .catch(function (error) { showToast(error.message, "error"); })
          .finally(function () { likeButton.disabled = false; });
      }
    });
    document.addEventListener("click", function (event) {
      if (!root.contains(event.target)) root.querySelectorAll(".wl-comment").forEach(function (node) { closePicker(node); });
    }, { signal: lifecycleSignal });
    function uploadImage(file, owner) {
      if (!file) return;
      if (file.size > 2 * 1024 * 1024) { showToast(message("ImageTooLarge", "Image must be smaller than 2 MB."), "error"); return; }
      var data = new FormData(); data.append("image", file, file.name || "pasted-image.png");
      fetch("/api/comments/upload/", { method: "POST", body: data, headers: { "X-CSRFToken": csrf(), Accept: "application/json" }, credentials: "same-origin" })
        .then(function (response) { return parseJsonResponse(response, message("UploadFailed", "Upload failed")); })
        .then(function (body) {
          if (!body.url) throw new Error(message("UploadUrlMissing", "Upload failed: server did not return an image URL."));
          var targetEditor = owner && owner.querySelector(".wl-editor");
          if (targetEditor) { targetEditor.value += "\n![image](" + body.url + ")\n"; targetEditor.dispatchEvent(new Event("input")); }
        })
        .catch(function (error) { showToast(error.message, "error"); });
    }
    root.addEventListener("change", function (event) {
      var imageInput = event.target.closest("[data-comment-image]");
      if (!imageInput || !imageInput.files.length) return;
      uploadImage(imageInput.files[0], imageInput.closest(".wl-comment"));
      imageInput.value = "";
    });
    function handleImagePaste(event) {
      var target = event.target.closest(".wl-editor");
      if (!target || !event.clipboardData || !event.clipboardData.items) return;
      var imageItem = null;
      for (var i = 0; i < event.clipboardData.items.length; i += 1) {
        if (event.clipboardData.items[i].type && event.clipboardData.items[i].type.indexOf("image/") === 0) { imageItem = event.clipboardData.items[i]; break; }
      }
      if (!imageItem && event.clipboardData.files && event.clipboardData.files.length) imageItem = event.clipboardData.files[0];
      if (!imageItem) return;
      var file = typeof imageItem.getAsFile === "function" ? imageItem.getAsFile() : imageItem;
      if (!file) return;
      event.preventDefault();
      uploadImage(file, target.closest(".wl-comment"));
    }
    root.addEventListener("paste", handleImagePaste, true);
    if (editor) editor.addEventListener("input", function () { var counter = composer.querySelector(".internal-comment-count"); if (counter) counter.textContent = editor.value.length + " / 5000"; if (preview && !preview.hidden) renderPreviewFor(composer); });
    load();
  }
  function boot() { document.querySelectorAll(".internal-comments").forEach(init); }
  // this script is reloaded after Swup inserts the new comment DOM, so binding
  // another permanent page:view hook here would leak one closure per visit
  boot();
})();
