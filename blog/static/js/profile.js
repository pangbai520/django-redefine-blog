(function () {
  "use strict";

  function initProfileForm() {
    var forms = Array.from(document.querySelectorAll("[data-profile-form]"));
    var cropModals = Array.from(document.querySelectorAll("[data-avatar-cropper]"));
    if (!forms.length) {
      cropModals.forEach(function (cropModal) {
        if (cropModal.dataset.profilePortal === "true") cropModal.remove();
      });
      document.body.classList.remove("profile-crop-open");
      return;
    }

    var modal = cropModals.find(function (cropModal) {
      return cropModal.dataset.profilePortal !== "true";
    }) || cropModals[0];
    if (!modal) return;
    cropModals.forEach(function (cropModal) {
      if (cropModal !== modal) cropModal.remove();
    });
    if (modal.parentNode !== document.body) document.body.appendChild(modal);
    modal.dataset.profilePortal = "true";

    forms.forEach(function (form) {
      if (form.dataset.profileReady === "true") return;
      form.dataset.profileReady = "true";

      var displayInput = form.querySelector('input[name="display_name"]');
      var displayPreview = document.querySelector("[data-profile-display-preview]");
      var avatarInput = document.querySelector("[data-avatar-input]");
      var avatarPreview = document.querySelector("[data-profile-avatar-preview]");
      var avatarTrigger = document.querySelector("[data-avatar-trigger]");
      var removeInput = document.querySelector("[data-avatar-remove-input]");
      var removeTrigger = document.querySelector("[data-avatar-remove-trigger]");
      var cropX = document.querySelector("[data-crop-x]");
      var cropY = document.querySelector("[data-crop-y]");
      var cropSize = document.querySelector("[data-crop-size]");
      if (!avatarInput || !avatarPreview || !avatarTrigger || !modal) return;

      var canvas = modal.querySelector("[data-crop-canvas]");
      var context = canvas && canvas.getContext("2d");
      var zoomInput = modal.querySelector("[data-crop-zoom]");
      var applyButton = modal.querySelector("[data-crop-apply]");
      var errorBox = modal.querySelector("[data-crop-error]");
      var state = {
        image: null,
        objectUrl: "",
        minScale: 1,
        scale: 1,
        offsetX: 0,
        offsetY: 0,
        pointerId: null,
        pointerX: 0,
        pointerY: 0
      };

      function fallbackName() {
        return (displayInput && displayInput.value.trim()) ||
          (displayPreview && displayPreview.dataset.fallback) || "?";
      }

      function replaceAvatarContent(node) {
        Array.from(avatarPreview.children).forEach(function (child) {
          if (!child.classList.contains("profile-avatar-edit-badge")) child.remove();
        });
        avatarPreview.insertBefore(node, avatarPreview.firstChild);
      }

      function showFallbackAvatar() {
        var initial = document.createElement("span");
        initial.className = "profile-avatar-initial";
        initial.textContent = fallbackName().slice(0, 1).toUpperCase();
        replaceAvatarContent(initial);
        avatarPreview.classList.remove("has-image");
      }

      function showAvatarImage(source) {
        var image = document.createElement("img");
        image.alt = "";
        image.src = source;
        replaceAvatarContent(image);
        avatarPreview.classList.add("has-image");
      }

      if (displayInput && displayPreview) {
        displayInput.addEventListener("input", function () {
          displayPreview.textContent = fallbackName();
          var initial = avatarPreview.querySelector(".profile-avatar-initial");
          if (initial) initial.textContent = fallbackName().slice(0, 1).toUpperCase();
        });
      }

      function clearError() {
        errorBox.hidden = true;
        errorBox.textContent = "";
      }

      function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
        applyButton.disabled = true;
      }

      function openModal() {
        modal.hidden = false;
        document.body.classList.add("profile-crop-open");
        applyButton.disabled = !state.image;
        requestAnimationFrame(function () { modal.querySelector(".profile-crop-close").focus(); });
      }

      function releaseObjectUrl() {
        if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
        state.objectUrl = "";
      }

      function closeModal(clearSelection) {
        modal.hidden = true;
        document.body.classList.remove("profile-crop-open");
        state.image = null;
        releaseObjectUrl();
        clearError();
        if (clearSelection) {
          avatarInput.value = "";
          cropX.value = "";
          cropY.value = "";
          cropSize.value = "";
        }
        avatarTrigger.focus();
      }

      function clampOffsets() {
        var scaledWidth = state.image.naturalWidth * state.scale;
        var scaledHeight = state.image.naturalHeight * state.scale;
        state.offsetX = Math.min(0, Math.max(canvas.width - scaledWidth, state.offsetX));
        state.offsetY = Math.min(0, Math.max(canvas.height - scaledHeight, state.offsetY));
      }

      function drawCrop() {
        if (!state.image || !context) return;
        clampOffsets();
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.drawImage(
          state.image,
          state.offsetX,
          state.offsetY,
          state.image.naturalWidth * state.scale,
          state.image.naturalHeight * state.scale
        );
      }

      function loadSelectedFile() {
        var file = avatarInput.files && avatarInput.files[0];
        if (!file) return;
        var supportedType = /^image\/(jpeg|png|gif|webp)$/i.test(file.type || "") ||
          /\.(jpe?g|png|gif|webp)$/i.test(file.name || "");
        clearError();
        openModal();
        if (!supportedType) {
          showError(modal.dataset.msgInvalidType);
          return;
        }

        releaseObjectUrl();
        state.objectUrl = URL.createObjectURL(file);
        var image = new Image();
        image.onload = function () {
          state.image = image;
          state.minScale = Math.max(
            canvas.width / image.naturalWidth,
            canvas.height / image.naturalHeight
          );
          state.scale = state.minScale;
          state.offsetX = (canvas.width - image.naturalWidth * state.scale) / 2;
          state.offsetY = (canvas.height - image.naturalHeight * state.scale) / 2;
          zoomInput.value = "1";
          applyButton.disabled = false;
          drawCrop();
        };
        image.onerror = function () { showError(modal.dataset.msgLoadFailed); };
        image.src = state.objectUrl;
      }

      avatarTrigger.addEventListener("click", function () { avatarInput.click(); });
      avatarInput.addEventListener("change", loadSelectedFile);

      modal.querySelectorAll("[data-crop-close]").forEach(function (button) {
        button.addEventListener("click", function () { closeModal(true); });
      });

      zoomInput.addEventListener("input", function () {
        if (!state.image) return;
        var imageCenterX = (canvas.width / 2 - state.offsetX) / state.scale;
        var imageCenterY = (canvas.height / 2 - state.offsetY) / state.scale;
        state.scale = state.minScale * Number(zoomInput.value);
        state.offsetX = canvas.width / 2 - imageCenterX * state.scale;
        state.offsetY = canvas.height / 2 - imageCenterY * state.scale;
        drawCrop();
      });

      canvas.addEventListener("pointerdown", function (event) {
        if (!state.image) return;
        state.pointerId = event.pointerId;
        state.pointerX = event.clientX;
        state.pointerY = event.clientY;
        canvas.setPointerCapture(event.pointerId);
      });
      canvas.addEventListener("pointermove", function (event) {
        if (event.pointerId !== state.pointerId || !state.image) return;
        var rect = canvas.getBoundingClientRect();
        state.offsetX += (event.clientX - state.pointerX) * canvas.width / rect.width;
        state.offsetY += (event.clientY - state.pointerY) * canvas.height / rect.height;
        state.pointerX = event.clientX;
        state.pointerY = event.clientY;
        drawCrop();
      });
      ["pointerup", "pointercancel"].forEach(function (eventName) {
        canvas.addEventListener(eventName, function (event) {
          if (event.pointerId === state.pointerId) state.pointerId = null;
        });
      });

      applyButton.addEventListener("click", function () {
        if (!state.image) return;
        clampOffsets();
        cropX.value = String(Math.max(0, -state.offsetX / state.scale));
        cropY.value = String(Math.max(0, -state.offsetY / state.scale));
        cropSize.value = String(canvas.width / state.scale);
        showAvatarImage(canvas.toDataURL("image/webp", 0.9));
        if (removeInput) removeInput.checked = false;
        if (removeTrigger) removeTrigger.hidden = false;
        closeModal(false);
      });

      if (removeTrigger && removeInput) {
        removeTrigger.addEventListener("click", function () {
          removeInput.checked = true;
          avatarInput.value = "";
          cropX.value = "";
          cropY.value = "";
          cropSize.value = "";
          showFallbackAvatar();
          removeTrigger.hidden = true;
        });
      }

      modal.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeModal(true);
      });
    });
  }

  initProfileForm();
  document.addEventListener("swup:contentReplaced", initProfileForm);
})();
