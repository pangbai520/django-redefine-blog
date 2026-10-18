let lazyLoadObserver = null;

export default function initLazyLoad() {
  lazyLoadObserver?.disconnect();

  const imgs = document.querySelectorAll("img");
  if (typeof window.IntersectionObserver === "undefined") {
    imgs.forEach((img) => {
      if (img.hasAttribute("lazyload") && img.dataset.src) {
        img.src = img.dataset.src;
        img.removeAttribute("lazyload");
      }
    });
    return;
  }
  const options = {
    rootMargin: "0px",
    threshold: 0.1,
  };
  lazyLoadObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const img = entry.target;
        const source = img.getAttribute("data-src");
        if (source) img.src = source;
        img.removeAttribute("lazyload");
        observer.unobserve(img);
      }
    });
  }, options);
  imgs.forEach((img) => {
    if (img.hasAttribute("lazyload")) {
      lazyLoadObserver.observe(img);
    }
  });
}
