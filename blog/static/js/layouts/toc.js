/* rebuild TOC state per page, so Swup never keeps headings from the previous article */

import { initTocToggle } from "../tools/tocToggle.js";
import { getStyleStatus } from "../themeState.js";
export function initTOC() {
  const utils = {
    navItems: document.querySelectorAll(".post-toc-wrap .post-toc li"),

    updateActiveTOCLink() {
      if (!Array.isArray(utils.sections)) return;
      let index = utils.sections.findIndex((element) => {
        return element && element.getBoundingClientRect().top - 100 > 0;
      });
      if (index === -1) {
        index = utils.sections.length - 1;
      } else if (index > 0) {
        index--;
      }
      this.activateTOCLink(index);
    },

    registerTOCScroll() {
      utils.sections = [
        ...document.querySelectorAll(".post-toc li a.nav-link"),
      ].map((element) => {
        const target = document.getElementById(
          decodeURI(element.getAttribute("href")).replace("#", ""),
        );
        return target;
      });
    },

    activateTOCLink(index) {
      const target = document.querySelectorAll(".post-toc li a.nav-link")[
        index
      ];

      if (!target || target.classList.contains("active-current")) {
        return;
      }

      document.querySelectorAll(".post-toc .active").forEach((element) => {
        element.classList.remove("active", "active-current");
      });
      target.classList.add("active", "active-current");
      // center the active entry, so long outlines remain readable while scrolling
      const tocElement = document.querySelector(".toc-content-container");
      const tocTop = tocElement.getBoundingClientRect().top;
      const scrollTopOffset =
        tocElement.offsetHeight > window.innerHeight
          ? (tocElement.offsetHeight - window.innerHeight) / 2
          : 0;
      const targetTop = target.getBoundingClientRect().top - tocTop;
      const viewportHeight = Math.max(
        document.documentElement.clientHeight,
        window.innerHeight || 0,
      );
      const distanceToCenter =
        targetTop -
        viewportHeight / 2 +
        target.offsetHeight / 2 -
        scrollTopOffset;
      const scrollTop = tocElement.scrollTop + distanceToCenter;

      tocElement.scrollTo({
        top: scrollTop,
        behavior: "smooth",
      });
    },

    showTOCAside() {
      const openHandle = () => {
        const styleStatus = getStyleStatus();
        const key = "isOpenPageAside";
        if (styleStatus && styleStatus.hasOwnProperty(key)) {
          initTocToggle().pageAsideHandleOfTOC(styleStatus[key]);
        } else {
          initTocToggle().pageAsideHandleOfTOC(true);
        }
      };

      const initOpenKey = "init_open";

      if (theme.articles.toc.hasOwnProperty(initOpenKey)) {
        theme.articles.toc[initOpenKey]
          ? openHandle()
          : initTocToggle().pageAsideHandleOfTOC(false);
      } else {
        openHandle();
      }
    },
  };

  if (utils.navItems.length > 0) {
    utils.showTOCAside();
    utils.registerTOCScroll();
  } else {
    document
      .querySelectorAll(".toc-content-container, .toc-marker")
      .forEach((elem) => {
        elem.remove();
      });
  }

  return utils;
}
