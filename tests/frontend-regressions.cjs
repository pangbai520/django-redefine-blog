// run production modules against small DOM fixtures, so regressions stay testable without npm packages
const assert = require('node:assert/strict');
const { existsSync, readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const blogRoot = [
  path.join(__dirname, '../pangbaiblog/blog'),
  path.join(__dirname, '../blog'),
].find(existsSync);
if (!blogRoot) throw new Error('Could not locate the Django blog application.');
const jsRoot = path.join(blogRoot, 'static/js');
const source = (name) => readFileSync(path.join(jsRoot, name), 'utf8');
const flush = () => new Promise((resolve) => setImmediate(resolve));
const withoutImports = (value) => value.replace(/^import[\s\S]*?;\r?\n/gm, '');
const loadThemeState = (context) => vm.runInContext(
  source('themeState.js').replaceAll('export const ', 'const '),
  context,
);

test('custom TOC widths only override the desktop layout', () => {
  const overrides = readFileSync(
    path.join(blogRoot, 'templates/components/header/theme-overrides.html'),
    'utf8',
  );
  assert.match(
    overrides,
    /@media \(min-width: 769px\) \{[\s\S]*?\.post-page-container\.show-toc \.article-content-container \{[\s\S]*?width: calc\(100% - var\(--site-toc-sidebar-width\)\) !important;/,
  );
});

test('footer runtime uses one short odometer animation instead of a perpetual transition', () => {
  const scripts = readFileSync(
    path.join(blogRoot, 'templates/components/scripts.html'),
    'utf8',
  );
  const runtime = source('tools/runtime.js');
  const styles = readFileSync(path.join(blogRoot, 'static/css/style.css'), 'utf8');
  assert.match(scripts, /odometerOptions = \{ auto: false \}/);
  assert.doesNotMatch(scripts, /static 'js\/tools\/runtime\.js'/);
  assert.match(runtime, /duration: 200/);
  assert.match(runtime, /let runtimeTimer = null/);
  assert.match(runtime, /export default function initFooterRuntime/);
  assert.doesNotMatch(runtime, /setInterval/);
  assert.match(styles, /\.footer \.odometer[\s\S]*?transition: transform 200ms;/);
  assert.doesNotMatch(styles, /\.footer \.odometer[\s\S]*?transition: transform 999ms;/);
});

test('short pages keep a stable mobile viewport height without a scripted footer margin', () => {
  const base = readFileSync(path.join(blogRoot, 'templates/base.html'), 'utf8');
  const styles = readFileSync(path.join(blogRoot, 'static/css/style.css'), 'utf8');
  const utils = source('utils.js');
  assert.match(base, /main-content-container[^\n]*stable-viewport-height/);
  assert.doesNotMatch(base, /main-content-container[^\n]*min-h-dvh/);
  assert.match(styles, /\.main-content-container \{[\s\S]*?min-height: 100vh;/);
  assert.match(styles, /@supports \(min-height: 100lvh\)[\s\S]*?min-height: 100lvh;/);
  assert.doesNotMatch(utils, /initPageHeightHandle/);
  assert.doesNotMatch(utils, /\.main-content-footer["']\)[\s\S]*?style\.marginTop/);
});

test('article avatars use the generated non-shrinking utility from upstream', () => {
  const article = readFileSync(
    path.join(blogRoot, 'templates/pages/post/article-content.html'),
    'utf8',
  );
  const tailwind = readFileSync(
    path.join(blogRoot, 'static/css/build/tailwind.css'),
    'utf8',
  );
  assert.match(article, /class="avatar[^\"]*\bshrink-0\b/);
  assert.doesNotMatch(article, /\bflex-shrink-0\b/);
  assert.match(tailwind, /\.shrink-0\{flex-shrink:0\}/);
});

test('profile avatars use the cropper and transparent-image background', () => {
  const profile = readFileSync(
    path.join(blogRoot, 'templates/comments/profile.html'),
    'utf8',
  );
  const script = source('profile.js');
  const styles = readFileSync(path.join(blogRoot, 'static/css/profile.css'), 'utf8');
  const commentStyles = readFileSync(
    path.join(blogRoot, 'static/css/internal-comments.css'),
    'utf8',
  );
  assert.match(profile, /data-avatar-trigger/);
  assert.match(profile, /data-avatar-cropper/);
  assert.match(profile, /data-crop-canvas/);
  assert.doesNotMatch(profile, /profile-preview-picker/);
  assert.doesNotMatch(profile, /fa-crop-simple/);
  assert.doesNotMatch(profile, /profile-avatar-hint/);
  assert.doesNotMatch(profile, /profile-heading-icon/);
  assert.match(profile, /page-title-header profile-heading-title/);
  assert.match(profile, /field\.name == "old_password"[\s\S]*?password_reset/);
  assert.match(script, /cropX\.value/);
  assert.match(script, /canvas\.toDataURL\("image\/webp"/);
  assert.match(script, /document\.body\.appendChild\(modal\)/);
  assert.match(styles, /\.profile-avatar-preview\.has-image \{ background: var\(--background-color\); \}/);
  assert.match(styles, /\.profile-page \.page-template-content \{ padding: 0; \}/);
  assert.match(commentStyles, /img\.wl-user-avatar \{ background: var\(--background-color\); \}/);
});

class Element {
  constructor(classes = []) {
    this.classes = new Set(classes);
    this.classList = {
      add: (...names) => names.forEach((name) => this.classes.add(name)),
      remove: (...names) => names.forEach((name) => this.classes.delete(name)),
      contains: (name) => this.classes.has(name),
      toggle: (name, force = !this.classes.has(name)) => {
        force ? this.classes.add(name) : this.classes.delete(name);
        return force;
      },
      [Symbol.iterator]: () => this.classes.values(),
    };
    this.listeners = new Map();
    this.dataset = {};
    this.style = {};
    this.value = '';
    this.innerHTML = '';
    this.attributes = {};
  }
  addEventListener(type, handler, { signal } = {}) {
    if (signal?.aborted) return;
    const handlers = this.listeners.get(type) || new Set();
    handlers.add(handler);
    this.listeners.set(type, handlers);
    signal?.addEventListener('abort', () => handlers.delete(handler), { once: true });
  }
  removeEventListener(type, handler) {
    this.listeners.get(type)?.delete(handler);
  }
  emit(type, target = this) {
    for (const handler of this.listeners.get(type) || []) {
      handler({ target, preventDefault() {}, stopPropagation() {} });
    }
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

function searchFixture(fetch) {
  const input = new Element();
  const result = new Element();
  const overlay = new Element();
  const trigger = new Element();
  const close = new Element();
  const document = new Element();
  document.body = new Element();
  document.querySelector = (selector) => ({
    '.search-input': input,
    '.search-pop-overlay': overlay,
    '.popup-btn-close': close,
  })[selector] || null;
  document.querySelectorAll = () => [trigger];
  document.getElementById = () => result;
  const window = new Element();
  const context = vm.createContext({
    document, window, AbortController, fetch, console: { warn() {} },
    // Run the short search debounce while ignoring the focus animation timer.
    setTimeout(callback, delay) { if (delay < 500) callback(); return 1; },
    clearTimeout() {}, config: { root: '/', path: '/search.json' },
    theme: { navbar: { search: { top_n_per_article: 3 } } },
  });
  vm.runInContext(source('tools/localSearch.js').replace('export default ', ''), context);
  context.initLocalSearch();
  return { context, input, result, overlay, trigger, close };
}

const response = (rows) => ({ ok: true, text: async () => JSON.stringify(rows) });

test('search renders a query typed before the index arrives, with one pending request', async () => {
  let resolve;
  let requests = 0;
  const fixture = searchFixture(() => {
    requests++;
    return new Promise((done) => { resolve = done; });
  });
  fixture.trigger.emit('click');
  fixture.trigger.emit('click');
  fixture.input.value = 'needle';
  fixture.input.emit('input');
  assert.equal(requests, 1);
  resolve(response([{ title: 'needle article', content: '', url: '/needle/' }]));
  await flush();
  assert.match(fixture.result.innerHTML, /search-keyword.*needle/);
  assert.match(fixture.result.innerHTML, /href="\/needle\/"/);
});

test('search prioritizes complete phrase matches before loose word hit counts', async () => {
  const fixture = searchFixture(async () => response([
    { title: 'complete', content: 'alpha beta', url: '/complete/' },
    { title: 'loose', content: 'alpha alpha alpha separated beta beta beta', url: '/loose/' },
  ]));
  fixture.input.value = 'alpha beta';
  fixture.trigger.emit('click');
  await flush();
  const html = fixture.result.innerHTML;
  assert.ok(html.indexOf('/complete/') < html.indexOf('/loose/'));
});

test('search escapes indexed text and preserves encoded and absolute URLs', async () => {
  const fixture = searchFixture(async () => response([
    { title: '<img src=x onerror=alert(1)> needle & "title"', content: '', url: '/a%22b%2Fc/' },
    { title: '<unsafe> & "unhighlighted"', content: 'needle', url: 'https://example.com/a?x=1&y=2' },
  ]));
  fixture.input.value = 'needle';
  fixture.trigger.emit('click');
  await flush();
  const html = fixture.result.innerHTML;
  assert.ok(!html.includes('<img'));
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /&lt;unsafe&gt; &amp; &quot;unhighlighted&quot;/);
  assert.match(html, /href="\/a%22b%2Fc\/"/);
  assert.match(html, /href="https:\/\/example.com\/a\?x=1&amp;y=2"/);
});

test('failed search requests show a retry state and can be retried on reopening', async () => {
  let requests = 0;
  const fixture = searchFixture(async () => ++requests === 1
    ? { ok: false, status: 503 }
    : response([{ title: 'needle', content: '', url: '/recovered/' }]));
  fixture.input.value = 'needle';
  fixture.trigger.emit('click');
  await flush();
  assert.match(fixture.result.innerHTML, /role="status"/);
  fixture.close.emit('click');
  fixture.trigger.emit('click');
  await flush();
  assert.equal(requests, 2);
  assert.match(fixture.result.innerHTML, /\/recovered\//);
});

test('search refresh aborts old requests and prevents stale result writes', async () => {
  const pending = [];
  const fixture = searchFixture((url, { signal }) => new Promise((resolve) => {
    pending.push({ resolve, signal });
  }));
  fixture.input.value = 'needle';
  fixture.trigger.emit('click');
  fixture.context.initLocalSearch();
  assert.equal(pending[0].signal.aborted, true);
  assert.equal(fixture.overlay.classList.contains('active'), false);
  fixture.trigger.emit('click');
  assert.equal(pending.length, 2);
  pending[1].resolve(response([{ title: 'needle new', content: '', url: '/new/' }]));
  await flush();
  pending[0].resolve(response([{ title: 'needle stale', content: '', url: '/stale/' }]));
  await flush();
  assert.match(fixture.result.innerHTML, /\/new\//);
  assert.ok(!fixture.result.innerHTML.includes('/stale/'));
});

test('tabs respond to icon clicks, preserve nested tabs, and bind once across refreshes', () => {
  const document = new Element();
  const tabs = new Element();
  const nav = new Element();
  const oldItem = new Element(['active']);
  const newItem = new Element();
  const link = new Element(['#pane-2']);
  link.parentElement = newItem;
  link.closest = () => tabs;
  const first = new Element(['active']);
  const second = new Element();
  first.id = 'pane-1';
  second.id = 'pane-2';
  first.closest = second.closest = () => tabs;
  const nested = new Element(['active']);
  nested.closest = () => new Element();
  nav.querySelectorAll = () => [link];
  nav.querySelector = () => oldItem.classList.contains('active') ? oldItem : newItem;
  tabs.querySelectorAll = () => [first, second, nested];
  document.querySelectorAll = () => [nav];
  let refresh;
  const swup = { hooks: { on(name, handler) { refresh = handler; } } };
  const context = vm.createContext({ document, AbortController, swup,
    window: { swup },
  });
  vm.runInContext(source('plugins/tabs.js'), context);
  document.emit('DOMContentLoaded');
  refresh();
  assert.equal(link.listeners.get('click').size, 1);
  link.emit('click', new Element()); // nested icon is the event target
  assert.equal(oldItem.classList.contains('active'), false);
  assert.equal(newItem.classList.contains('active'), true);
  assert.equal(first.classList.contains('active'), false);
  assert.equal(second.classList.contains('active'), true);
  assert.equal(nested.classList.contains('active'), true);
});

test('bookmark navigation selects the first section and updates immediately on click', () => {
  const firstNav = new Element();
  const secondNav = new Element();
  firstNav.attributes['data-category'] = 'first';
  secondNav.attributes['data-category'] = 'second';

  const window = new Element();
  window.scrollY = 0;
  window.innerHeight = 500;
  const section = (id, top) => ({
    id,
    getBoundingClientRect: () => ({ top: top - window.scrollY }),
  });
  const sections = [section('first', 200), section('second', 600)];
  const page = {
    querySelectorAll: (selector) => selector === '.bookmark-nav-item'
      ? [firstNav, secondNav]
      : sections,
  };
  const document = {
    documentElement: { scrollHeight: 1200 },
    querySelector: (selector) => selector === '.bookmarks-page' ? page : null,
  };
  const context = vm.createContext({
    document, window, AbortController,
    setTimeout: (callback) => callback(),
    clearTimeout() {},
  });
  vm.runInContext(
    source('layouts/bookmarkNav.js').replace('export default ', ''),
    context,
  );

  context.initBookmarkNav();
  assert.equal(firstNav.classList.contains('active'), true);
  assert.equal(secondNav.classList.contains('active'), false);

  secondNav.emit('click');
  assert.equal(firstNav.classList.contains('active'), false);
  assert.equal(secondNav.classList.contains('active'), true);

  window.scrollY = 700;
  window.emit('scroll');
  assert.equal(firstNav.classList.contains('active'), false);
  assert.equal(secondNav.classList.contains('active'), true);

  context.initBookmarkNav();
  assert.equal(firstNav.listeners.get('click').size, 1);
  assert.equal(secondNav.listeners.get('click').size, 1);
});

test('disabling code copying does not disable highlighting or folding during page refresh', () => {
  const document = new Element();
  document.documentElement = new Element();
  document.documentElement.dataset.codeBlockCopy = 'false';
  document.getElementById = () => null;
  const copy = new Element();
  const fold = new Element();
  const controls = new Element();
  controls.querySelector = (selector) => selector === '.copy-button' ? copy : fold;
  const figure = new Element(['highlight', 'plaintext']);
  const line = { textContent: 'hello' };
  figure.querySelectorAll = () => [line];
  const container = new Element();
  container.querySelectorAll = () => [figure];
  container.querySelector = () => controls;
  document.querySelectorAll = () => [container];
  const noop = () => {};
  const context = vm.createContext({
    document, window: { theme: { articles: { code_block: { copy: false } } },
      hljs: { getLanguage: () => true }, swup: {} }, console,
    localStorage: { getItem: () => null, setItem() {} },
    initUtils: noop, initModeToggle: noop, initScrollTopBottom: noop,
    initLanguageSwitcher: noop,
    initBookmarkNav: noop, destroyTyped: noop, initTyped: noop,
    initHomeBanner: noop, updateArticleExpiration: noop,
    initLocalSearch: noop, initLazyLoad: noop,
  });
  vm.runInContext(source('tools/codeBlock.js').replace('export default initCopyCode;', ''), context);
  loadThemeState(context);
  vm.runInContext(withoutImports(source('main.js')).replace('export const main', 'const main'), context);
  vm.runInContext('main.refresh(); main.refresh();', context);
  assert.equal(copy.hidden, true);
  assert.equal(figure.dataset.highlighted, 'true');
  assert.equal(fold.listeners.get('click').size, 1);
  fold.emit('click');
  assert.equal(controls.classList.contains('folded'), true);
});

function modeFixture(defaultMode, savedStatus, systemDark = false) {
  const media = new Element();
  media.matches = systemDark;
  const window = { theme: { colors: { default_mode: defaultMode } }, matchMedia: () => media };
  const document = new Element();
  document.documentElement = new Element();
  const localStorage = {
    getItem: () => savedStatus === undefined ? null : JSON.stringify(savedStatus),
    setItem() {},
  };
  const context = vm.createContext({ document, window, localStorage, console, AbortController });
  loadThemeState(context);
  vm.runInContext(withoutImports(source('main.js')).replace('export const main', 'const main'), context);
  vm.runInContext(withoutImports(source('tools/lightDarkSwitch.js'))
    .replace('export const ModeToggle', 'const ModeToggle')
    .replace('export default ', ''), context);
  context.chosen = [];
  vm.runInContext(`
    ModeToggle.enableDarkMode = () => chosen.push('dark');
    ModeToggle.enableLightMode = () => chosen.push('light');
    ModeToggle.initModeStatus();
    ModeToggle.initModeAutoTrigger(new AbortController().signal);
  `, context);
  const head = readFileSync(path.join(blogRoot, 'templates/components/header/head.html'), 'utf8');
  const earlyThemeScript = head.match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/\{\{ site.colour_default_mode\|default:'light' \}\}/, defaultMode);
  vm.runInContext(earlyThemeScript, context);
  return { context, media, document };
}

test('configured defaults match the first paint and runtime even against system preference', () => {
  for (const [mode, systemDark] of [['light', true], ['dark', false]]) {
    const fixture = modeFixture(mode, undefined, systemDark);
    assert.equal(fixture.context.chosen[0], mode);
    assert.equal(fixture.document.documentElement.getAttribute('data-theme'), mode);
    fixture.media.emit('change');
    assert.equal(fixture.context.chosen.length, 1);
    assert.equal(fixture.document.documentElement.getAttribute('data-theme'), mode);
  }
});

test('saved user color choice overrides the configured default in first paint and runtime', () => {
  const fixture = modeFixture('dark', { isDark: false }, true);
  assert.equal(fixture.context.chosen[0], 'light');
  assert.equal(fixture.document.documentElement.getAttribute('data-theme'), 'light');
});

test('non-color saved preferences do not freeze automatic color mode', () => {
  const fixture = modeFixture('auto', {
    isDark: false,
    isColorModeExplicit: false,
    fontSizeLevel: 2,
    isOpenPageAside: true,
  }, true);
  assert.equal(fixture.context.chosen[0], 'dark');
  assert.equal(fixture.document.documentElement.getAttribute('data-theme'), 'dark');
  fixture.media.matches = false;
  fixture.media.emit('change');
  assert.equal(fixture.context.chosen.at(-1), 'light');
});

test('invalid saved state cannot inject truthy color flags or out-of-range font levels', () => {
  const fixture = modeFixture('light', { isDark: 'false', fontSizeLevel: 100, isOpenPageAside: 'false' }, true);
  assert.equal(fixture.context.chosen[0], 'light');
  assert.equal(fixture.document.documentElement.getAttribute('data-theme'), 'light');
  assert.equal(vm.runInContext('main.styleStatus.fontSizeLevel', fixture.context), 0);
  assert.equal(vm.runInContext('main.styleStatus.isOpenPageAside', fixture.context), true);
});

test('color initialization works without the matchMedia browser API', () => {
  const fixture = modeFixture('auto', undefined);
  delete fixture.context.window.matchMedia;
  fixture.context.chosen.length = 0;
  vm.runInContext('ModeToggle.initModeStatus()', fixture.context);
  assert.equal(fixture.context.chosen[0], 'light');
});

test('manual color changes fall back to an atomic swap without view transitions', () => {
  const frames = new Map();
  let nextFrame = 0;
  const document = new Element();
  document.body = new Element(['light-mode']);
  document.documentElement = new Element(['light', 'light-mode']);
  const window = {
    theme: { colors: { default_mode: 'light' } },
    requestAnimationFrame(callback) {
      const id = ++nextFrame;
      frames.set(id, callback);
      return id;
    },
    cancelAnimationFrame(id) { frames.delete(id); },
  };
  const localStorage = { getItem: () => null, setItem() {} };
  const context = vm.createContext({ document, window, localStorage, console, AbortController });
  loadThemeState(context);
  vm.runInContext(withoutImports(source('tools/lightDarkSwitch.js'))
    .replace('export default ', ''), context);

  vm.runInContext('ModeToggle.enableDarkMode()', context);
  assert.equal(document.documentElement.classList.contains('theme-switching'), true);
  assert.equal(document.body.classList.contains('dark-mode'), true);
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');

  const firstFrame = frames.values().next().value;
  frames.clear();
  firstFrame();
  assert.equal(document.documentElement.classList.contains('theme-switching'), true);
  const releaseFrame = frames.values().next().value;
  frames.clear();
  releaseFrame();
  assert.equal(document.documentElement.classList.contains('theme-switching'), false);
});

test('manual color changes use one coordinated view transition when supported', async () => {
  const document = new Element();
  document.body = new Element(['light-mode']);
  document.documentElement = new Element(['light', 'light-mode']);
  let starts = 0;
  document.startViewTransition = (update) => {
    starts += 1;
    update();
    return { finished: Promise.resolve(), skipTransition() {} };
  };
  const window = {
    theme: { colors: { default_mode: 'light' } },
    matchMedia: () => ({ matches: false }),
  };
  const localStorage = { getItem: () => null, setItem() {} };
  const context = vm.createContext({ document, window, localStorage, console, AbortController });
  loadThemeState(context);
  vm.runInContext(withoutImports(source('tools/lightDarkSwitch.js'))
    .replace('export default ', ''), context);

  vm.runInContext('ModeToggle.enableDarkMode()', context);
  assert.equal(starts, 1);
  assert.equal(document.documentElement.classList.contains('theme-switching'), true);
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
  await flush();
  assert.equal(document.documentElement.classList.contains('theme-switching'), false);
});

test('a named DOM element exposed as window.swup is not treated as a Swup instance', () => {
  const document = new Element();
  document.getElementById = () => null;
  const context = vm.createContext({
    document,
    window: { theme: {}, swup: new Element() },
    localStorage: { getItem: () => null, setItem() {} },
    console,
    initUtils() {}, initModeToggle() {}, initScrollTopBottom() {},
    initBookmarkNav() {}, destroyTyped() {}, initTyped() {}, initLocalSearch() {},
    initHomeBanner() {}, updateArticleExpiration() {},
    initCopyCode() {}, initLazyLoad() {},
  });
  loadThemeState(context);
  assert.doesNotThrow(() => vm.runInContext(
    withoutImports(source('main.js')).replace('export const main', 'const main'),
    context,
  ));
});

test('article expiration is refreshed from the current Swup page data', () => {
  const label = new Element();
  label.textContent = 'This post is written __DAYS__ days ago, and the content may not be up to date.';
  const expiration = new Element(['hidden']);
  expiration.dataset.expiresAt = '2001-01-01T00:00:00Z';
  expiration.dataset.updatedAt = '2000-01-01T00:00:00Z';
  expiration.querySelector = () => label;
  const document = { querySelectorAll: () => [expiration] };
  const context = vm.createContext({ document, Date });
  vm.runInContext(
    source('layouts/articleExpiration.js').replace('export default ', ''),
    context,
  );
  context.updateArticleExpiration();
  assert.equal(expiration.classList.contains('hidden'), false);
  assert.match(
    label.textContent,
    /^This post is written \d+ days ago, and the content may not be up to date\.$/,
  );
});

test('home banner scroll action is rebound once after a page refresh', () => {
  const button = new Element();
  const target = new Element();
  let scrolls = 0;
  target.scrollIntoView = ({ behavior }) => {
    assert.equal(behavior, 'smooth');
    scrolls += 1;
  };
  const document = {
    querySelector: (selector) => selector === '[data-scroll-to-main]' ? button : target,
  };
  const context = vm.createContext({ document, AbortController });
  vm.runInContext(
    source('layouts/homeBanner.js').replace('export default ', ''),
    context,
  );
  context.initHomeBanner();
  context.initHomeBanner();
  assert.equal(button.listeners.get('click').size, 1);
  button.emit('click');
  assert.equal(scrolls, 1);
});

test('language switcher opens, closes, and rebinds once after a page refresh', () => {
  const trigger = new Element();
  const modal = new Element();
  const dialog = new Element();
  const option = new Element();
  const close = new Element();
  modal.hidden = true;
  modal.querySelector = (selector) => ({
    '.language-switcher-dialog': dialog,
    '.language-switcher-option': option,
  })[selector] || null;
  modal.querySelectorAll = () => [close];
  const document = new Element();
  document.body = new Element();
  document.querySelector = (selector) => ({
    '.tool-language-switch': trigger,
    '[data-language-switcher-modal]': modal,
  })[selector] || null;
  const window = {
    requestAnimationFrame: (callback) => callback(),
    setTimeout: (callback) => callback(),
  };
  const context = vm.createContext({ document, window, AbortController });
  vm.runInContext(
    source('tools/languageSwitcher.js').replace('export default ', ''),
    context,
  );
  context.initLanguageSwitcher();
  context.initLanguageSwitcher();
  assert.equal(trigger.listeners.get('click').size, 1);
  trigger.emit('click');
  assert.equal(modal.hidden, false);
  assert.equal(modal.classList.contains('is-open'), true);
  assert.equal(document.body.classList.contains('language-switcher-open'), true);
  assert.equal(option.focused, true);
  close.emit('click');
  assert.equal(modal.hidden, true);
  assert.equal(document.body.classList.contains('language-switcher-open'), false);
  assert.equal(trigger.focused, true);
});

test('navbar shrink state is recalculated after a Swup visit', () => {
  const navbar = new Element();
  navbar.getBoundingClientRect = () => ({ height: 80 });
  const body = new Element(['navbar-shrink']);
  body.scrollTop = 0;
  const document = new Element();
  document.body = body;
  document.documentElement = { scrollTop: 200 };
  document.querySelector = (selector) => selector === '.navbar-container' ? navbar : null;
  document.querySelectorAll = () => [];
  const hooks = new Map();
  const window = new Element();
  window.swup = { hooks: { on: (name, handler) => hooks.set(name, handler) } };
  const context = vm.createContext({
    document,
    window,
    navigationState: { isNavigating: false },
    anime: Object.assign(() => {}, { stagger: () => 0 }),
  });
  vm.runInContext(withoutImports(source('layouts/navbarShrink.js')), context);
  document.emit('DOMContentLoaded');
  assert.equal(body.classList.contains('navbar-shrink'), true);
  hooks.get('visit:start')();
  assert.equal(body.classList.contains('navbar-shrink'), false);
  hooks.get('page:view')();
  assert.equal(body.classList.contains('navbar-shrink'), true);
});

test('Mermaid restores source and renders the current page using the active mode', async () => {
  const attributes = new Map();
  const node = {
    textContent: 'graph TD; A-->B',
    hasAttribute: (name) => attributes.has(name),
    setAttribute: (name, value) => attributes.set(name, value),
    getAttribute: (name) => attributes.get(name) ?? null,
    removeAttribute: (name) => attributes.delete(name),
  };
  const calls = [];
  const document = {
    documentElement: { getAttribute: () => 'dark' },
    querySelectorAll: () => [node],
  };
  const window = {
    theme: {
      plugins: { mermaid: { enable: true } },
      mermaid: { style: { light: 'default', dark: 'forest' } },
    },
    mermaid: {
      initialize: (options) => calls.push(['initialize', options]),
      run: async (options) => {
        calls.push(['run', options]);
        node.textContent = '<svg>rendered</svg>';
      },
    },
  };
  const context = vm.createContext({ document, window, console });
  vm.runInContext(source('plugins/mermaid.js'), context);
  await window.redefineMermaid.render();
  assert.equal(calls[0][1].theme, 'forest');
  assert.equal(calls[1][1].nodes[0], node);
  node.textContent = 'stale svg';
  await window.redefineMermaid.render('neutral');
  assert.equal(calls[2][1].theme, 'neutral');
  assert.equal(attributes.get('data-original-code'), 'graph TD; A-->B');
});
