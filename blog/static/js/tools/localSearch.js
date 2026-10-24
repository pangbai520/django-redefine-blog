let localSearchController = null;
let closeCurrentSearch = () => {};
let swupCloseHookRegistered = false;

export default function initLocalSearch() {
  closeCurrentSearch();
  localSearchController?.abort();
  localSearchController = new AbortController();
  const { signal } = localSearchController;

  // read the generated index path from Django's browser config, so deployments
  // can move the site root without changing this module
  let searchPath = config.path;
  if (!searchPath) {
    console.warn("The local search index path is not configured.");
    return;
  }

  // keep each bounded server result inside this page lifecycle, so an aborted
  // Swup visit cannot write stale results into the next page
  let fetchPromise = null;
  let datas = [];
  let fetchedQuery = "";
  let pendingQuery = "";
  let requestFailed = false;
  let requestSequence = 0;
  let debounceTimer = null;
  const searchInputDom = document.querySelector(".search-input");
  const resultContent = document.getElementById("search-result");
  const overlayDom = document.querySelector(".search-pop-overlay");
  if (!searchInputDom || !resultContent || !overlayDom) return;

  const getIndexByWord = (word, text, caseSensitive) => {
    let wordLen = word.length;
    if (wordLen === 0) return [];
    let startPosition = 0;
    let position = [];
    let index = [];
    if (!caseSensitive) {
      text = text.toLowerCase();
      word = word.toLowerCase();
    }
    while ((position = text.indexOf(word, startPosition)) > -1) {
      index.push({ position, word });
      startPosition = position + wordLen;
    }
    return index;
  };

  // merge nearby hits into one excerpt, so results stay compact and readable
  const mergeIntoSlice = (start, end, index, searchText) => {
    let currentItem = index[index.length - 1];
    let { position, word } = currentItem;
    let hits = [];
    let searchTextCountInSlice = 0;

    while (position + word.length <= end && index.length !== 0) {
      if (word === searchText) {
        searchTextCountInSlice++;
      }
      hits.push({
        position,
        length: word.length,
      });

      const wordEnd = position + word.length;

      // skip overlapping hits, so highlighted ranges never duplicate text
      index.pop();
      for (let i = index.length - 1; i >= 0; i--) {
        currentItem = index[i];
        position = currentItem.position;
        word = currentItem.word;
        if (wordEnd <= position) {
          break;
        } else {
          index.pop();
        }
      }
    }

    return {
      hits,
      start,
      end,
      searchTextCount: searchTextCountInSlice,
    };
  };

  // escape indexed content before adding highlight markup, so search data
  // cannot inject arbitrary HTML into the popup
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);

  const highlightKeyword = (text, slice) => {
    let result = "";
    let prevEnd = slice.start;
    slice.hits.forEach((hit) => {
      result += escapeHtml(text.substring(prevEnd, hit.position));
      let end = hit.position + hit.length;
      result += `<b class="search-keyword">${escapeHtml(text.substring(
        hit.position,
        end,
      ))}</b>`;
      prevEnd = end;
    });
    result += escapeHtml(text.substring(prevEnd, slice.end));
    return result;
  };

  const inputEventFunction = () => {
    let searchText = searchInputDom.value.trim().toLowerCase();
    let keywords = searchText.split(/[-\s]+/);
    if (keywords.length > 1) {
      keywords.push(searchText);
    }
    let resultItems = [];
    if (searchText.length > 0) {
      // search titles and plain-text content together, so either can surface a result
      datas.forEach(({ title, content, url }) => {
        let titleInLowerCase = title.toLowerCase();
        let contentInLowerCase = content.toLowerCase();
        let indexOfTitle = [];
        let indexOfContent = [];
        let searchTextCount = 0;
        keywords.forEach((keyword) => {
          indexOfTitle = indexOfTitle.concat(
            getIndexByWord(keyword, titleInLowerCase, false),
          );
          indexOfContent = indexOfContent.concat(
            getIndexByWord(keyword, contentInLowerCase, false),
          );
        });

        if (indexOfTitle.length > 0 || indexOfContent.length > 0) {
          let hitCount = indexOfTitle.length + indexOfContent.length;
          // sort backwards, because mergeIntoSlice consumes matches from the end
          [indexOfTitle, indexOfContent].forEach((index) => {
            index.sort((itemLeft, itemRight) => {
              if (itemRight.position !== itemLeft.position) {
                return itemRight.position - itemLeft.position;
              }
              return itemLeft.word.length - itemRight.word.length;
            });
          });

          let slicesOfTitle = [];
          if (indexOfTitle.length !== 0) {
            let tmp = mergeIntoSlice(0, title.length, indexOfTitle, searchText);
            searchTextCount += tmp.searchTextCount;
            slicesOfTitle.push(tmp);
          }

          let slicesOfContent = [];
          while (indexOfContent.length !== 0) {
            let item = indexOfContent[indexOfContent.length - 1];
            let { position, word } = item;
            // keep roughly 100 characters around each match, so snippets stay concise
            let start = position - 20;
            let end = position + 80;
            if (start < 0) {
              start = 0;
            }
            if (end < position + word.length) {
              end = position + word.length;
            }
            if (end > content.length) {
              end = content.length;
            }
            let tmp = mergeIntoSlice(start, end, indexOfContent, searchText);
            searchTextCount += tmp.searchTextCount;
            slicesOfContent.push(tmp);
          }

          // prefer exact phrases, then denser keyword matches, so useful excerpts rank first
          slicesOfContent.sort((sliceLeft, sliceRight) => {
            if (sliceLeft.searchTextCount !== sliceRight.searchTextCount) {
              return sliceRight.searchTextCount - sliceLeft.searchTextCount;
            } else if (sliceLeft.hits.length !== sliceRight.hits.length) {
              return sliceRight.hits.length - sliceLeft.hits.length;
            }
            return sliceLeft.start - sliceRight.start;
          });

          // respect Redefine's per-article limit, so one article cannot dominate the popup
          let upperBound = parseInt(
            theme.navbar.search.top_n_per_article
              ? theme.navbar.search.top_n_per_article
              : 1,
            10,
          );
          if (upperBound >= 0) {
            slicesOfContent = slicesOfContent.slice(0, upperBound);
          }

          let resultItem = "";

          const escapedUrl = escapeHtml(url);
          if (slicesOfTitle.length !== 0) {
            resultItem += `<li><a href="${escapedUrl}" class="search-result-title">${highlightKeyword(
              title,
              slicesOfTitle[0],
            )}</a>`;
          } else {
            resultItem += `<li><a href="${escapedUrl}" class="search-result-title">${escapeHtml(title)}</a>`;
          }

          slicesOfContent.forEach((slice) => {
            resultItem += `<a href="${escapedUrl}"><p class="search-result">${highlightKeyword(
              content,
              slice,
            )}...</p></a>`;
          });

          resultItem += "</li>";
          resultItems.push({
            item: resultItem,
            id: resultItems.length,
            hitCount,
            searchTextCount,
          });
        }
      });
    }
    if (keywords.length === 1 && keywords[0] === "") {
      resultContent.innerHTML =
        '<div id="no-result"><i class="fa-solid fa-magnifying-glass fa-5x"></i></div>';
    } else if (resultItems.length === 0) {
      resultContent.innerHTML =
        '<div id="no-result"><i class="fa-solid fa-box-open fa-5x"></i></div>';
    } else {
      resultItems.sort((resultLeft, resultRight) => {
        if (resultLeft.searchTextCount !== resultRight.searchTextCount) {
          return resultRight.searchTextCount - resultLeft.searchTextCount;
        } else if (resultLeft.hitCount !== resultRight.hitCount) {
          return resultRight.hitCount - resultLeft.hitCount;
        }
        return resultRight.id - resultLeft.id;
      });
      let searchResultList = '<ul class="search-result-list">';
      resultItems.forEach((result) => {
        searchResultList += result.item;
      });
      searchResultList += "</ul>";
      resultContent.innerHTML = searchResultList;
      window.pjax && window.pjax.refresh(resultContent);
    }
  };

  const fetchData = (query, force = false) => {
    query = query.trim();
    if (!query) {
      datas = [];
      fetchedQuery = "";
      inputEventFunction();
      return Promise.resolve();
    }
    if (!force && (fetchedQuery === query || pendingQuery === query)) {
      inputEventFunction();
      return fetchPromise || Promise.resolve();
    }

    const sequence = ++requestSequence;
    const separator = searchPath.includes("?") ? "&" : "?";
    const baseUrl = searchPath.startsWith("/") ? searchPath : `${config.root}${searchPath}`;
    const url = `${baseUrl}${separator}q=${encodeURIComponent(query)}`;
    pendingQuery = query;
    fetchPromise = fetch(url, { signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Search index HTTP ${response.status}`);
        return response.text();
      })
      .then((res) => {
        if (signal.aborted || sequence !== requestSequence) return;
        const payload = JSON.parse(res);
        datas = Array.isArray(payload) ? payload : payload.results || [];
        // discard untitled entries, because they cannot produce accessible result links
        datas = datas
          .filter((data) => data.title)
          .map((data) => {
            data.title = data.title.trim();
            data.content = data.content
              ? data.content.trim().replace(/<[^>]+>/g, "")
              : "";
            // preserve encoded paths and absolute URL separators, so indexed links
            // are not corrupted by a second normalization pass
            data.url = String(data.url || "");
            return data;
          });
        fetchedQuery = query;
        requestFailed = false;
        if (searchInputDom.value.trim() === query) inputEventFunction();
      })
      .catch((error) => {
        if (signal.aborted || sequence !== requestSequence) return;
        requestFailed = true;
        console.warn("Unable to load search index:", error);
        resultContent.innerHTML = '<div id="no-result" role="status">Unable to load search. Please reopen to retry.</div>';
      })
      .finally(() => {
        if (sequence === requestSequence) {
          pendingQuery = "";
          fetchPromise = null;
        }
      });
    return fetchPromise;
  };

  const requestCurrentSearch = ({ immediate = false, force = false } = {}) => {
    const query = searchInputDom.value.trim();
    clearTimeout(debounceTimer);
    if (!query) {
      datas = [];
      fetchedQuery = "";
      inputEventFunction();
      return;
    }
    const run = () => {
      resultContent.innerHTML = '<div id="no-result"><i class="fa-solid fa-spinner fa-spin-pulse fa-5x fa-fw"></i></div>';
      fetchData(query, force);
    };
    if (immediate) run();
    else debounceTimer = setTimeout(run, 180);
  };

  if (searchInputDom) {
    searchInputDom.addEventListener("input", () => requestCurrentSearch(), { signal });
  }

  // bind every desktop and mobile trigger to the same overlay lifecycle
  document.querySelectorAll(".search-popup-trigger").forEach((element) => {
    element.addEventListener("click", () => {
      document.body.style.overflow = "hidden";
      overlayDom.classList.add("active");
      setTimeout(() => {
        if (!signal.aborted && overlayDom.classList.contains("active")) searchInputDom.focus();
      }, 500);
      requestCurrentSearch({ immediate: true, force: requestFailed });
    }, { signal });
  });

  // restore body scrolling on every close path, including Swup and Escape
  const onPopupClose = () => {
    document.body.style.overflow = "";
    overlayDom.classList.remove("active");
  };
  closeCurrentSearch = onPopupClose;

  overlayDom.addEventListener("click", (event) => {
      if (event.target === overlayDom) {
        onPopupClose();
      }
    }, { signal });
  document.querySelector(".search-input-field-pre")?.addEventListener("click", () => {
      searchInputDom.value = "";
      searchInputDom.focus();
      requestCurrentSearch({ immediate: true });
    }, { signal });
  document.querySelector(".popup-btn-close")?.addEventListener(
    "click",
    onPopupClose,
    { signal },
  );

  if (!swupCloseHookRegistered && window.swup?.hooks) {
    window.swup.hooks.on("page:view", () => closeCurrentSearch());
    swupCloseHookRegistered = true;
  }

  window.addEventListener("keyup", (event) => {
    if (event.key === "Escape") {
      onPopupClose();
    }
  }, { signal });
}
