/* keep the TOC toggle state outside the page DOM, so it survives Swup navigation */

import { setStyleStatus, styleStatus } from "../themeState.js";

let activeTocToggle = null;
let tocToggleController = null;

export function initTocToggle() {
  const toggleBar = document.querySelector(".page-aside-toggle");
  if (activeTocToggle?.toggleBar === toggleBar) return activeTocToggle;

  tocToggleController?.abort();
  tocToggleController = new AbortController();
  const { signal } = tocToggleController;

  const TocToggle = {
    toggleBar,
    postPageContainerDom: document.querySelector(".post-page-container"),
    toggleBarIcon: document.querySelector(".page-aside-toggle i"),
    articleContentContainerDom: document.querySelector(
      ".article-content-container",
    ),
    mainContentDom: document.querySelector(".main-content"),

    isOpenPageAside: false,

    initToggleBarButton() {
      this.toggleBar &&
        this.toggleBar.addEventListener("click", () => {
          this.isOpenPageAside = !this.isOpenPageAside;
          styleStatus.isOpenPageAside = this.isOpenPageAside;
          setStyleStatus();
          this.changePageLayoutWhenOpenToggle(this.isOpenPageAside);
        }, { signal });
    },

    toggleClassName(element, className, condition) {
      if (element) {
        element.classList.toggle(className, condition);
      }
    },
    changePageLayoutWhenOpenToggle(isOpen) {
      this.toggleClassName(this.toggleBarIcon, "fas", isOpen);
      this.toggleClassName(this.toggleBarIcon, "fa-indent", isOpen);
      this.toggleClassName(this.toggleBarIcon, "fa-outdent", !isOpen);
      this.toggleClassName(this.postPageContainerDom, "show-toc", isOpen);
      this.toggleClassName(this.mainContentDom, "has-toc", isOpen);
    },

    pageAsideHandleOfTOC(isOpen) {
      if (!this.toggleBar) return;
      this.toggleBar.style.display = "flex";
      this.isOpenPageAside = isOpen;
      this.changePageLayoutWhenOpenToggle(isOpen);
    },
  };

  TocToggle.initToggleBarButton();
  activeTocToggle = TocToggle;
  return TocToggle;
}
