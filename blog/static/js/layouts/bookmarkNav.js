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

    let frameId = 0;
    const setActiveNavItem = (preferredSectionId = null) => {
        const fromTop = window.scrollY + 100;
        let currentSection = sections[0];

        if (preferredSectionId) {
            currentSection = sections.find(
                (section) => section.id === preferredSectionId,
            ) || currentSection;
        } else if (
            window.scrollY > 0 &&
            window.scrollY + window.innerHeight >=
                document.documentElement.scrollHeight - 2
        ) {
            currentSection = sections.at(-1);
        } else {
            for (const section of sections) {
                if (fromTop >= section.offsetTop) currentSection = section;
            }
        }

        for (const item of navItems) {
            item.classList.toggle(
                "active",
                item.dataset.category === currentSection.id,
            );
        }
    };

    for (const item of navItems) {
        item.addEventListener(
            "click",
            () => setActiveNavItem(item.dataset.category),
            { signal },
        );
    }

    window.addEventListener(
        "scroll",
        () => {
            if (frameId) return;
            frameId = window.requestAnimationFrame(() => {
                frameId = 0;
                setActiveNavItem();
            });
        },
        { passive: true, signal },
    );
    signal.addEventListener(
        "abort",
        () => window.cancelAnimationFrame(frameId),
        { once: true },
    );

    setActiveNavItem(window.location.hash.slice(1) || null);
}
