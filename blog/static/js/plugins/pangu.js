function initPanguJS() {
  // space mixed CJK and Latin text after every page swap, matching Hexo's filter
  pangu.spacingElementByClassName("markdown-body");

  pangu.autoSpacingPage();
}

document.addEventListener("DOMContentLoaded", initPanguJS);

if (window.swup?.hooks) {
  window.swup.hooks.on("page:view", initPanguJS);
}
