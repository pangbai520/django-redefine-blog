let bookmarkNavController = null;

export default function initBookmarkNav() {
    bookmarkNavController?.abort();
    bookmarkNavController = new AbortController();
    const { signal } = bookmarkNavController;

    const page = document.querySelector(".bookmarks-page");
    if (!page) return;

    const navItems = Array.from(page.querySelectorAll(".bookmark-nav-item"));
    const sections = Array.from(
        page.querySelectorAll("section.bookmark-section[id]"),
    );
    if (!navItems.length || !sections.length) return;

    const throttle = (callback, delay) => {
        let waiting = false;
        return () => {
            if (waiting) return;
            callback();
            waiting = true;
            window.setTimeout(() => {
                waiting = false;
            }, delay);
        };
    };

    // Redefine 2.8.2 only applies the muted background while scrolling.
    // Do not replace this with the later active/scale interaction.
    const setActiveNavItem = () => {
        const fromTop = window.scrollY + 100;
        let currentSection = null;

        for (const section of sections) {
            const sectionTop = section.offsetTop;
            const sectionBottom = sectionTop + section.offsetHeight;
            if (fromTop >= sectionTop && fromTop < sectionBottom) {
                currentSection = section;
            }
        }

        for (const item of navItems) {
            item.classList.remove("bg-second-background-color");
            if (
                currentSection &&
                item.dataset.category === currentSection.id
            ) {
                item.classList.add("bg-second-background-color");
            }
        }
    };

    window.addEventListener(
        "scroll",
        throttle(setActiveNavItem, 100),
        { passive: true, signal },
    );

    setActiveNavItem();
}
