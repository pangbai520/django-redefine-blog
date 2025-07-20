// format stored timestamps in the reader's locale, so essays retain Redefine's calendar labels
function formatEssayDates() {
  const dateElements = document.querySelectorAll(".essay-date");

  if (!dateElements) {
    return;
  }

  dateElements.forEach(function (element) {
    const rawDate = element.getAttribute("data-date");
    const locale = config.language || "en";

    const formattedDate = moment(rawDate).locale(locale).calendar();
    element.textContent = formattedDate;
  });
}

if (window.swup?.hooks) {
  window.swup.hooks.on("page:view", formatEssayDates);
}

// cover the initial document here, while the Swup hook handles later page views
document.addEventListener("DOMContentLoaded", formatEssayDates);
