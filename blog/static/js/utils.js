/* coordinate shared page behavior, so one abortable lifecycle owns every global listener */
import { initTOC } from "./layouts/toc.js";
import { getStyleStatus, setStyleStatus, styleStatus } from "./themeState.js";
import imageViewer from "./tools/imageViewer.js";

let utilsController = null;

export const navigationState = {
  isNavigating: false,
};

export default function initUtils() {
  utilsController?.abort();
  utilsController = new AbortController();
  const { signal } = utilsController;

  const utils = {
    html_root_dom: document.querySelector("html"),
    pageTop_dom: document.querySelector(".main-content-header"),
    homeBanner_dom: document.querySelector(".home-banner-container"),
    homeBannerBackground_dom: document.querySelector(".home-banner-background"),
    scrollProgressBar_dom: document.querySelector(".scroll-progress-bar"),
    backToTopButton_dom: document.querySelector(".tool-scroll-to-top"),
    toolsList: document.querySelector(".hidden-tools-list"),
    toggleButton: document.querySelector(".toggle-tools-list"),

    innerHeight: window.innerHeight,
    prevScrollValue: 0,
    triggerViewHeight: 0.5 * window.innerHeight,

    tocController: null,
    isHasScrollProgressBar:
      window.theme?.global?.scroll_progress?.bar === true,
    isHasScrollPercent:
      window.theme?.global?.scroll_progress?.percentage === true,

    // update related scroll UI together, so progress, TOC and navbar state share one frame
    updateScrollStyle() {
      const scrollTop =
        window.pageYOffset || document.documentElement.scrollTop;
      const scrollHeight = document.documentElement.scrollHeight;
      const clientHeight =
        window.innerHeight || document.documentElement.clientHeight;
      const percent = this.calculatePercentage(
        scrollTop,
        scrollHeight,
        clientHeight,
      );

      this.updateScrollProgressBar(percent);
      this.updateScrollPercent(percent);
      this.updatePageTopVisibility(scrollTop, clientHeight);

      this.prevScrollValue = scrollTop;
    },

    updateScrollProgressBar(percent) {
      if (this.isHasScrollProgressBar && this.scrollProgressBar_dom) {
        const progressPercent = percent.toFixed(3);
        const visibility = percent === 0 ? "hidden" : "visible";

        this.scrollProgressBar_dom.style.visibility = visibility;
        this.scrollProgressBar_dom.style.width = `${progressPercent}%`;
      }
    },

    updateScrollPercent(percent) {
      if (this.isHasScrollPercent && this.backToTopButton_dom) {
        const percentDom = this.backToTopButton_dom.querySelector(".percent");
        const showButton = percent !== 0 && percent !== undefined;

        this.backToTopButton_dom.classList.toggle("show", showButton);
        if (percentDom) percentDom.innerHTML = percent.toFixed(0);
      }
    },

    updatePageTopVisibility(scrollTop, clientHeight) {
      if (!this.pageTop_dom) return;
      if (window.theme?.navbar?.auto_hide) {
        const prevScrollValue = this.prevScrollValue;
        const hidePageTop =
          prevScrollValue > clientHeight && scrollTop > prevScrollValue;

        this.pageTop_dom.classList.toggle("hide", hidePageTop);
      } else {
        this.pageTop_dom.classList.remove("hide");
      }
    },

    calculatePercentage(scrollTop, scrollHeight, clientHeight) {
      let percentageValue = Math.round(
        (scrollTop / (scrollHeight - clientHeight)) * 100,
      );
      if (
        isNaN(percentageValue) ||
        percentageValue < 0 ||
        !isFinite(percentageValue)
      ) {
        percentageValue = 0;
      } else if (percentageValue > 100) {
        percentageValue = 100;
      }
      return percentageValue;
    },

    // attach abortable listeners, so Swup refreshes replace rather than duplicate them
    registerWindowScroll() {
      window.addEventListener("scroll", () => {
        this.updateScrollStyle();
        this.updateTOCScroll();
        this.updateAutoHideTools();
      }, { passive: true, signal });
      window.addEventListener(
        "scroll",
        this.debounce(() => this.updateHomeBannerBlur(), 20),
        { passive: true, signal },
      );
    },

    updateTOCScroll() {
      this.tocController?.updateActiveTOCLink?.();
    },

    debounce(func, delay) {
      let timer;
      return function () {
        clearTimeout(timer);
        timer = setTimeout(() => func.apply(this, arguments), delay);
      };
    },

    updateHomeBannerBlur() {
      if (!this.homeBannerBackground_dom) return;

      if (
        window.theme?.home_banner?.style === "fixed" &&
        location.pathname === config.root
      ) {
        const scrollY = window.scrollY || window.pageYOffset;
        const blurValue = scrollY >= this.triggerViewHeight ? 15 : 0;

        try {
          requestAnimationFrame(() => {
            this.homeBannerBackground_dom.style.filter = `blur(${blurValue}px)`;
            this.homeBannerBackground_dom.style.webkitFilter = `blur(${blurValue}px)`;
          });
        } catch (error) {
          console.error("Unable to update the home banner blur:", error);
        }
      }
    },

    updateAutoHideTools() {
      const y = window.scrollY;
      const height = document.body.scrollHeight;
      const windowHeight = window.innerHeight;
      const toolList = document.getElementsByClassName(
        "right-side-tools-container",
      );
      const aplayer = document.getElementById("aplayer");

      for (let i = 0; i < toolList.length; i++) {
        const tools = toolList[i];
        if (y <= 100) {
          if (location.pathname === config.root) {
            tools.classList.add("hide");
            if (aplayer !== null) {
              aplayer.classList.add("hide");
            }
          } else {
            tools.classList.remove("hide");
            aplayer?.classList.remove("hide");
          }
        } else if (y + windowHeight >= height - 20) {
          tools.classList.add("hide");
          if (aplayer !== null) {
            aplayer.classList.add("hide");
          }
        } else {
          tools.classList.remove("hide");
          if (aplayer !== null) {
            aplayer.classList.remove("hide");
          }
        }
      }
    },

    toggleToolsList() {
      // apply the configured initial state before binding the toggle, so the
      // first paint and later clicks agree
      if (!this.toolsList || !this.toggleButton) return;

      if (window.theme?.global?.side_tools?.auto_expand) {
        this.toolsList.classList.add("show");
      }

      this.toggleButton.addEventListener("click", () => {
        this.toolsList.classList.toggle("show");
      }, { signal });
    },

    fontAdjPlus_dom: document.querySelector(".tool-font-adjust-plus"),
    fontAdMinus_dom: document.querySelector(".tool-font-adjust-minus"),
    globalFontSizeAdjust() {
      const htmlRoot = this.html_root_dom;
      const fontAdjustPlus = this.fontAdjPlus_dom;
      const fontAdjustMinus = this.fontAdMinus_dom;
      if (!htmlRoot || !document.body || !fontAdjustPlus || !fontAdjustMinus) {
        return;
      }

      const fontSize = document.defaultView.getComputedStyle(
        document.body,
      ).fontSize;
      const baseFontSize = parseFloat(fontSize);

      let fontSizeLevel = 0;
      const savedStyleStatus = getStyleStatus();
      if (savedStyleStatus) {
        fontSizeLevel = Number.isFinite(Number(savedStyleStatus.fontSizeLevel))
          ? Number(savedStyleStatus.fontSizeLevel)
          : 0;
        setFontSize(fontSizeLevel);
      }

      function setFontSize(level) {
        const fontSize = baseFontSize * (1 + level * 0.05);
        htmlRoot.style.fontSize = `${fontSize}px`;
        styleStatus.fontSizeLevel = level;
        setStyleStatus();
      }

      function increaseFontSize() {
        fontSizeLevel = Math.min(fontSizeLevel + 1, 5);
        setFontSize(fontSizeLevel);
      }

      function decreaseFontSize() {
        fontSizeLevel = Math.max(fontSizeLevel - 1, 0);
        setFontSize(fontSizeLevel);
      }

      fontAdjustPlus.addEventListener("click", increaseFontSize, { signal });
      fontAdjustMinus.addEventListener("click", decreaseFontSize, { signal });
    },
    // scroll to the current comment anchor, so external comment providers work too
    goComment() {
      this.goComment_dom = document.querySelector(".go-comment");
      if (this.goComment_dom) {
        this.goComment_dom.addEventListener("click", () => {
          const target = document.querySelector("#comment-anchor");
          if (target) {
            const offset = target.getBoundingClientRect().top + window.scrollY;
            window.scrollTo({
              top: offset,
              behavior: "smooth",
            });
          }
        }, { signal });
      }
    },

    // match the banner to the live viewport, so mobile browser chrome does not clip it
    inithomeBannerHeight() {
      this.homeBanner_dom &&
        (this.homeBanner_dom.style.height = this.innerHeight + "px");
    },

    setHowLongAgoLanguage(p1, p2) {
      return p2.replace(/%s/g, p1);
    },

    getHowLongAgo(timestamp) {
      const l = window.lang_ago || {
        year: "%s years ago",
        month: "%s months ago",
        week: "%s weeks ago",
        day: "%s days ago",
        hour: "%s hours ago",
        minute: "%s minutes ago",
        second: "%s seconds ago",
      };

      const __Y = Math.floor(timestamp / (60 * 60 * 24 * 30) / 12);
      const __M = Math.floor(timestamp / (60 * 60 * 24 * 30));
      const __W = Math.floor(timestamp / (60 * 60 * 24) / 7);
      const __d = Math.floor(timestamp / (60 * 60 * 24));
      const __h = Math.floor((timestamp / (60 * 60)) % 24);
      const __m = Math.floor((timestamp / 60) % 60);
      const __s = Math.floor(timestamp % 60);

      if (__Y > 0) {
        return this.setHowLongAgoLanguage(__Y, l.year);
      } else if (__M > 0) {
        return this.setHowLongAgoLanguage(__M, l.month);
      } else if (__W > 0) {
        return this.setHowLongAgoLanguage(__W, l.week);
      } else if (__d > 0) {
        return this.setHowLongAgoLanguage(__d, l.day);
      } else if (__h > 0) {
        return this.setHowLongAgoLanguage(__h, l.hour);
      } else if (__m > 0) {
        return this.setHowLongAgoLanguage(__m, l.minute);
      } else if (__s > 0) {
        return this.setHowLongAgoLanguage(__s, l.second);
      }
      return this.setHowLongAgoLanguage(0, l.second);
    },

    relativeTimeInHome() {
      const post = document.querySelectorAll(
        ".home-article-meta-info .home-article-date",
      );
      const df = window.theme?.home?.article_date_format;
      if (df === "relative") {
        post &&
          post.forEach((v) => {
            const nowDate = Date.now();
            const postDate = new Date(
              v.dataset.date.split(" GMT")[0],
            ).getTime();
            v.innerHTML = this.getHowLongAgo(
              Math.floor((nowDate - postDate) / 1000),
            );
          });
      } else if (df === "auto") {
        post &&
          post.forEach((v) => {
            const nowDate = Date.now();
            const postDate = new Date(
              v.dataset.date.split(" GMT")[0],
            ).getTime();
            const finalDays = Math.floor(
              (nowDate - postDate) / (60 * 60 * 24 * 1000),
            );
            if (finalDays < 7) {
              v.innerHTML = this.getHowLongAgo(
                Math.floor((nowDate - postDate) / 1000),
              );
            }
          });
      }
    },
  };

  if (
    window.theme?.articles?.toc?.enable &&
    document.querySelector(".post-toc li a.nav-link")
  ) {
    utils.tocController = initTOC();
  }

  utils.updateAutoHideTools();
  utils.updateScrollStyle();

  utils.registerWindowScroll();
  window.addEventListener("resize", () => {
    utils.innerHeight = window.innerHeight;
    utils.triggerViewHeight = 0.5 * window.innerHeight;
    utils.inithomeBannerHeight();
    utils.updateScrollStyle();
  }, { passive: true, signal });

  utils.toggleToolsList();
  utils.globalFontSizeAdjust();
  utils.goComment();
  utils.inithomeBannerHeight();
  utils.relativeTimeInHome();
  imageViewer();
}
