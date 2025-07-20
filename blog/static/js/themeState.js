export const localStorageKey = "REDEFINE-THEME-STATUS";

export const styleStatus = {
  isExpandPageWidth: false,
  isDark: window.theme?.colors?.default_mode === "dark",
  isColorModeExplicit: false,
  fontSizeLevel: 0,
  isOpenPageAside: true,
};

export const setStyleStatus = () => {
  try {
    localStorage.setItem(localStorageKey, JSON.stringify(styleStatus));
  } catch (error) {
    console.warn("Unable to save theme status:", error);
  }
};

export const getStyleStatus = () => {
  try {
    const savedValue = localStorage.getItem(localStorageKey);
    if (!savedValue) return null;

    const savedStatus = JSON.parse(savedValue);
    if (!savedStatus || typeof savedStatus !== "object") return null;

    const isLegacyColorChoice =
      !Object.prototype.hasOwnProperty.call(savedStatus, "isColorModeExplicit") &&
      typeof savedStatus.isDark === "boolean";

    Object.keys(styleStatus).forEach((key) => {
      const value = savedStatus[key];
      const valid = key === "fontSizeLevel"
        ? Number.isInteger(value) && value >= 0 && value <= 5
        : typeof value === "boolean";
      if (Object.prototype.hasOwnProperty.call(savedStatus, key) && valid) {
        styleStatus[key] = value;
      }
    });
    if (isLegacyColorChoice) styleStatus.isColorModeExplicit = true;
    return { ...styleStatus };
  } catch (error) {
    console.warn("Unable to restore theme status:", error);
    return null;
  }
};
