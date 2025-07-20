(function () {
  const container = document.getElementById("aplayer");
  const tracksElement = document.getElementById("aplayer-tracks");
  const settingsElement = document.getElementById("aplayer-settings");

  if (!container || !tracksElement || !window.APlayer) return;

  const parseJson = (element, fallback) => {
    try {
      return JSON.parse(element.textContent || "");
    } catch (error) {
      return fallback;
    }
  };

  const tracks = parseJson(tracksElement, []);
  const parsedSettings = parseJson(settingsElement, {});
  const settings = parsedSettings && typeof parsedSettings === "object"
    && !Array.isArray(parsedSettings) ? parsedSettings : {};
  if (!Array.isArray(tracks) || tracks.length === 0) return;

  const audio = tracks
    .filter((track) => track && track.url)
    .map((track) => ({
      name: track.name || "Untitled",
      artist: track.artist || "",
      url: track.url,
      cover: track.cover || "",
      lrc: track.lrc || "",
      theme: track.theme || "",
    }));
  if (audio.length === 0) return;

  const type = settings.type === "mini" ? "mini" : "fixed";
  const options = {
    ...settings,
    container,
    audio,
    mini: type === "mini",
    fixed: type === "fixed",
    lrcType: type === "fixed" ? 3 : 0,
  };

  const player = new window.APlayer(options);
  window.aplayer = player;

  if (type === "fixed") {
    // restore the info panel in fixed mode, because this bundled APlayer hides it by default
    player.setMode("normal");
    player.template.info.style.display = "block";
    const lrcButton = container.querySelector(".aplayer-icon-lrc");
    if (lrcButton) lrcButton.click();
  }
})();
