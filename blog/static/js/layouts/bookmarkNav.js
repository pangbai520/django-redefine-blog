let bookmarkNavController = null;

export default function initBookmarkNav() {
  bookmarkNavController?.abort();
  bookmarkNavController = new AbortController();
  const { signal } = bookmarkNavController;

  const page = document.querySelector('.bookmarks-page');
  if (!page) return;

  const navItems = Array.from(page.querySelectorAll('.bookmark-nav-item'));
  const sections = Array.from(
    page.querySelectorAll('section.bookmark-section[id]'),
  );

  if (!navItems.length || !sections.length) return;

  // replace the previous controller on every Swup refresh, so revisits cannot
  // accumulate scroll listeners or delayed callbacks
  function throttle(func, limit) {
    let lastCall = 0;
    let timer = null;
    const throttled = function(...args) {
      const remaining = limit - (Date.now() - lastCall);
      const invoke = () => {
        lastCall = Date.now();
        timer = null;
        func.apply(this, args);
      };

      if (remaining <= 0) {
        if (timer) clearTimeout(timer);
        invoke();
      } else {
        if (timer) clearTimeout(timer);
        timer = setTimeout(invoke, remaining);
      }
    };
    signal.addEventListener('abort', () => clearTimeout(timer), { once: true });
    return throttled;
  }

  function setActiveNavItem(preferredSectionId = null) {
    const fromTop = window.scrollY + 100;
    let currentSection = null;
    const documentHeight = document.documentElement?.scrollHeight || 0;
    const reachedPageBottom =
      window.scrollY > 0 &&
      documentHeight > 0 &&
      window.scrollY + window.innerHeight >= documentHeight - 2;

    if (preferredSectionId) {
      currentSection = sections.find(
        (section) => section.id === preferredSectionId,
      ) || null;
    } else if (reachedPageBottom) {
      currentSection = sections.at(-1);
    } else {
      sections.forEach((section) => {
        const sectionTop = section.getBoundingClientRect().top + window.scrollY;
        if (fromTop >= sectionTop) {
          currentSection = section;
        }
      });
    }

    navItems.forEach((item) => {
      const isActive =
        item.getAttribute('data-category') === currentSection?.id;
      item.classList.toggle('active', isActive);
    });
  }

  navItems.forEach((item) => {
    item.addEventListener('click', () => {
      const targetId = item.getAttribute('data-category');
      if (targetId) {
        // update before native hash scrolling starts, so the selected category
        // responds immediately and the scroll listener can maintain it afterward
        setActiveNavItem(targetId);
      }
    }, { signal });
  });

  // limit updates to once per 100 ms, so long bookmark pages scroll smoothly
  const onScroll = throttle(() => setActiveNavItem(), 100);
  window.addEventListener('scroll', onScroll, { passive: true, signal });

  // Match Redefine: the category navigation starts neutral and only becomes
  // active after its section reaches the reading position.
  setActiveNavItem();
}
