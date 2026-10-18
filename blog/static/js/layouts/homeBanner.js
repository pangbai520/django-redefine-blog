let homeBannerController = null;

export default function initHomeBanner() {
  homeBannerController?.abort();
  homeBannerController = new AbortController();
  const { signal } = homeBannerController;

  document.querySelector("[data-scroll-to-main]")?.addEventListener("click", () => {
    document.querySelector(".main-content-container")?.scrollIntoView({
      behavior: "smooth",
    });
  }, { signal });
}
