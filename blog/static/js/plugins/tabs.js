let tabsController = null;

function setTabs() {
  tabsController?.abort();
  tabsController = new AbortController();
  const { signal } = tabsController;
  let tabs = document.querySelectorAll(".tabs .nav-tabs");

  tabs.forEach((tab) => {
    tab.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();

        const parentTab = link.closest(".tabs");
        // read the pane hash from the bound anchor, so clicks on nested icons
        // and labels still activate the intended Redefine tab
        const hash = link.getAttribute("href") ||
          [...link.classList].find((name) => name.startsWith("#"));
        if (!parentTab || !hash?.startsWith("#")) return;
        const pane = [...parentTab.querySelectorAll(".tab-content .tab-pane")]
          .find((item) => item.id === hash.slice(1) && item.closest(".tabs") === parentTab);
        if (!pane) return;

        tab.querySelector(".active")?.classList.remove("active");
        link.parentElement.classList.add("active");
        parentTab.querySelectorAll(".tab-content .tab-pane").forEach((item) => {
          if (item.closest(".tabs") === parentTab) {
            item.classList.toggle("active", item === pane);
          }
        });

        return false;
      }, { signal });
    });
  });
}

if (window.swup?.hooks) {
  window.swup.hooks.on("page:view", setTabs);
}

document.addEventListener("DOMContentLoaded", setTabs);
