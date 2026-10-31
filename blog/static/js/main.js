/* keep one page lifecycle here, so Swup refreshes every migrated component consistently */
import initUtils, { isHomeFirstPage } from "./utils.js";
import initTyped, { destroyTyped } from "./plugins/typed.js";
import initModeToggle from "./tools/lightDarkSwitch.js";
import initLazyLoad from "./layouts/lazyload.js";
import initScrollTopBottom from "./tools/scrollTopBottom.js";
import initLanguageSwitcher from "./tools/languageSwitcher.js";
import initLocalSearch from "./tools/localSearch.js";
import initCopyCode from "./tools/codeBlock.js";
import updateArticleExpiration from "./layouts/articleExpiration.js";
import initHomeBanner from "./layouts/homeBanner.js";
import initFooterRuntime from "./tools/runtime.js";
import {
    getStyleStatus,
    localStorageKey,
    setStyleStatus,
    styleStatus,
} from "./themeState.js";

const main = {
    themeInfo: {
        theme: "Redefine Django Port",
        author: "Django Redefine contributors",
    },
    localStorageKey,
    styleStatus,
    setStyleStatus,
    getStyleStatus,

    refresh: () => {
        initUtils();
        initModeToggle();
        initScrollTopBottom();
        initLanguageSwitcher();
        initHomeBanner();
        if (document.getElementById("runtime_seconds")) {
            initFooterRuntime();
        }
        updateArticleExpiration();
        destroyTyped();

        const subtitleEl = document.getElementById('subtitle');
        if (
            subtitleEl &&
            window.theme?.home_banner?.subtitle?.enable &&
            isHomeFirstPage()
        ) {
            initTyped("subtitle");
        }

        if (window.theme?.navbar?.search?.enable) {
            initLocalSearch();
        }

        // keep highlighting and folding active when copying is disabled,
        // because the setting controls only the copy button
        initCopyCode();

        if (window.theme?.articles?.lazyload) {
            initLazyLoad();
        }
    },
};

const initMain = () => {
    console.log(`%c ${main.themeInfo.theme} %c`, 'color: #fff; background: #3b82f6; padding: 5px; border-radius: 3px;', '');
    main.refresh();
};

document.addEventListener("DOMContentLoaded", initMain);

if (window.swup?.hooks) {
    window.swup.hooks.on("page:view", () => {
        main.refresh();
    });
}
