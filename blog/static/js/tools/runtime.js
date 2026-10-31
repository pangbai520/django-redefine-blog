let runtimeTimer = null;

const runtimeElements = () => [
  document.getElementById("runtime_days"),
  document.getElementById("runtime_hours"),
  document.getElementById("runtime_minutes"),
  document.getElementById("runtime_seconds"),
];

const initializeOdometers = (elements) => {
  if (typeof window.Odometer !== "function") return;

  elements.filter(Boolean).forEach((element) => {
    if (element.odometer) return;
    new window.Odometer({
      el: element,
      format: "(,ddd)",
      duration: 200,
    });
  });
};

const renderFooterRuntime = () => {
  const startTime = window.theme?.footerStart;
  const elements = runtimeElements();
  if (!startTime || !elements.some(Boolean)) return false;

  const X = new Date(startTime);
  if (Number.isNaN(X.getTime())) return false;
  const Y = new Date();
  const T = Y.getTime() - X.getTime();
  const M = 24 * 60 * 60 * 1000;
  const a = T / M;
  const A = Math.floor(a);
  const b = (a - A) * 24;
  const B = Math.floor(b);
  const c = (b - B) * 60;
  const C = Math.floor((b - B) * 60);
  const D = Math.floor((c - C) * 60);

  initializeOdometers(elements);
  const values = [A, B, C, D];
  elements.forEach((element, index) => {
    if (element) element.innerHTML = values[index];
  });
  return true;
};

const footerRuntime = () => {
  runtimeTimer = null;
  if (!renderFooterRuntime()) return;
  runtimeTimer = window.setTimeout(footerRuntime, 1000);
};

export default function initFooterRuntime() {
  // A Swup refresh can replace the footer, so initialize the new elements now,
  // while keeping only one timer alive for the whole page lifecycle.
  renderFooterRuntime();
  if (runtimeTimer === null) {
    runtimeTimer = window.setTimeout(footerRuntime, 1000);
  }
}
