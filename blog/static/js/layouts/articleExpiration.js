export default function updateArticleExpiration() {
  document.querySelectorAll("[data-article-expiration]").forEach((container) => {
    const expiration = new Date(container.dataset.expiresAt || "");
    const updated = new Date(container.dataset.updatedAt || "");
    if (Number.isNaN(expiration.getTime()) || Number.isNaN(updated.getTime())) {
      container.classList.add("hidden");
      return;
    }

    const isExpired = expiration.getTime() < Date.now();
    container.classList.toggle("hidden", !isExpired);
    if (!isExpired) return;

    const value = container.querySelector("[data-expiration-date]");
    if (value) {
      const daysAgo = Math.max(
        0,
        Math.floor((Date.now() - updated.getTime()) / (1000 * 60 * 60 * 24)),
      );
      value.textContent = `expired ${daysAgo} days ago`;
    }
  });
}
