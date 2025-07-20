/* retain the original typed-banner behavior from @jiangwen5945 and EvanNotFound */
let typedInstance = null;
let typedRequestController = null;

export function destroyTyped() {
  typedRequestController?.abort();
  typedRequestController = null;
  typedInstance?.destroy();
  typedInstance = null;
}

export default function initTyped(id) {
  const target = document.getElementById(id);
  const subtitle = window.theme?.home_banner?.subtitle;
  if (!target || !subtitle?.enable || typeof window.Typed === "undefined") return;

  destroyTyped();

  const {
    typing_speed: typeSpeed = 100,
    backing_speed: backSpeed = 80,
    backing_delay: backDelay = 1500,
    starting_delay: startDelay = 500,
    loop = true,
    smart_backspace: smartBackspace = true,
  } = subtitle;

  function typing(dataList) {
    const strings = (Array.isArray(dataList) ? dataList : [dataList])
      .filter((item) => typeof item === "string" && item.trim());
    if (!strings.length) return;
    typedInstance = new Typed("#" + id, {
      strings,
      typeSpeed,
      smartBackspace,
      backSpeed,
      backDelay,
      loop,
      startDelay,
    });
  }

  if (subtitle.hitokoto?.enable) {
    typedRequestController = new AbortController();
    fetch(subtitle.hitokoto.api || "https://v1.hitokoto.cn", {
      signal: typedRequestController.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Hitokoto request failed (${response.status})`);
        return response.json();
      })
      .then((data) => {
        if (!document.getElementById(id)) return;
        if (!data || typeof data.hitokoto !== "string" || !data.hitokoto.trim()) {
          throw new Error("Hitokoto returned an empty sentence");
        }
        if (data.from_who && subtitle.hitokoto.show_author) {
          typing(data.hitokoto + "——" + data.from_who);
        } else {
          typing(data.hitokoto);
        }
      })
      .catch((error) => {
        if (error.name === "AbortError") return;
        console.error(error);
        if (document.getElementById(id)) typing(subtitle.text || []);
      });
  } else {
    const sentenceList = Array.isArray(subtitle.text) ? subtitle.text : [];
    if (sentenceList.length > 0) typing(sentenceList);
  }
}
