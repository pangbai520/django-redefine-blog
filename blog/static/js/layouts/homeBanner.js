let homeBannerController = null;

export default function initHomeBanner() {
  homeBannerController?.abort();
  homeBannerController = new AbortController();
  const { signal } = homeBannerController;

  const scrollControl = document.querySelector("[data-scroll-to-main]");
  const scrollToMain = () => {
    document.querySelector(".main-content-container")?.scrollIntoView({
      behavior: "smooth",
    });
  };

  scrollControl?.addEventListener("click", scrollToMain, { signal });
  scrollControl?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    scrollToMain();
  }, { signal });
}
