let masonryController = null;
let masonryInstance = null;
let masonryTimer = null;

function initMasonry() {
  masonryController?.abort();
  if (masonryTimer) clearTimeout(masonryTimer);
  masonryTimer = null;
  masonryInstance?.destroy?.();
  masonryInstance = null;
  masonryController = new AbortController();
  const { signal } = masonryController;

  var loadingPlaceholder = document.querySelector(".loading-placeholder");
  var masonryContainer = document.querySelector("#masonry-container");
  if (!loadingPlaceholder || !masonryContainer) return;

  loadingPlaceholder.style.display = "block";
  masonryContainer.style.display = "none";

  var images = document.querySelectorAll(
    "#masonry-container .masonry-item img",
  );
  var loadedCount = 0;
  var initialized = false;

  function onImageLoad() {
    loadedCount++;
    if (loadedCount === images.length) {
      initializeMasonryLayout();
    }
  }

  for (var i = 0; i < images.length; i++) {
    var img = images[i];
    if (img.complete) {
      onImageLoad();
    } else {
      img.addEventListener("load", onImageLoad, { signal });
      img.addEventListener("error", onImageLoad, { signal });
    }
  }

  if (loadedCount === images.length) {
    initializeMasonryLayout();
  }
  function initializeMasonryLayout() {
    if (initialized) return;
    initialized = true;
    loadingPlaceholder.style.opacity = 0;
    masonryTimer = setTimeout(() => {
      loadingPlaceholder.style.display = "none";
      masonryContainer.style.display = "block";
      var screenWidth = window.innerWidth;
      var baseWidth;
      if (screenWidth >= 768) {
        baseWidth = 255;
      } else {
        baseWidth = 150;
      }
      masonryInstance = new MiniMasonry({
        baseWidth: baseWidth,
        container: masonryContainer,
        gutterX: 10,
        gutterY: 10,
        surroundingGutter: false,
      });
      masonryInstance.layout();
      masonryContainer.style.opacity = 1;
    }, 100);
  }
}

if (window.swup?.hooks) {
  window.swup.hooks.on("page:view", initMasonry);
}

document.addEventListener("DOMContentLoaded", initMasonry);
