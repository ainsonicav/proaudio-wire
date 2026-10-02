/* ==========================================================================
   아인소닉 자료실 · library.js  v1.0.0
   www.ainsonic.com 과 news.ainsonic.com 이 같은 파일(복사본)을 씁니다.
   바꿀 것은 아래 API_URL 한 줄뿐입니다.
   ========================================================================== */
(function () {
  'use strict';

  /* ===== 설정 ===== */
  var API_URL = 'https://script.google.com/macros/s/AKfycbyuWVcR4abJa4RQWtGJhZdwsNTXhmeiIMhJJvpmu5eJrnRvIbaOawD0b0cwYV0YSgHf/exec';
  /* ================= */

  var CATEGORY_ORDER = ['카탈로그', '제안서', '브로슈어', '사양서', '매뉴얼', '가격표', '기타'];
  var SORTS = [['recommended', '추천순'], ['latest', '최신순'], ['popular', '인기순']];
  var CACHE_KEY = 'ains_lib_cache_v1';
  var TIMEOUT_MS = 15000;
  var SKELETON_COUNT = 6;

  var state = { items: [], cat: '', brand: '', q: '', sort: 'recommended', loaded: false };
  var ui = {};   // 화면 요소 모음

  /* ---------- 작은 도우미 ---------- */
  function el(tag, attrs, kids) {
    var n = document.createElement(tag), k;
    if (attrs) for (k in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, k) || attrs[k] == null) continue;
      if (k === 'text') n.textContent = attrs[k];
      else if (k === 'class') n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function str(v) { return v == null ? '' : String(v); }
  function norm(s) { return str(s).toLowerCase().replace(/\s+/g, ' ').trim(); }
  function safeUrl(u, prefixes) {
    u = str(u).trim();
    for (var i = 0; i < prefixes.length; i++) if (u.indexOf(prefixes[i]) === 0) return u;
    return '';
  }
  var HTTPS = ['https://'];
  var DRIVE = ['https://drive.google.com/'];

  /* ---------- 주소(URL)에 필터 상태 저장 · 복원 ---------- */
  function readQuery() {
    try {
      var p = new URLSearchParams(location.search);
      state.q = str(p.get('q'));
      state.cat = str(p.get('cat'));
      state.brand = str(p.get('brand'));
      var s = str(p.get('sort'));
      state.sort = SORTS.some(function (x) { return x[0] === s; }) ? s : 'recommended';
    } catch (e) { /* 오래된 브라우저는 기본값 */ }
  }
  function writeQuery() {
    try {
      var p = new URLSearchParams();
      if (state.q) p.set('q', state.q);
      if (state.cat) p.set('cat', state.cat);
      if (state.brand) p.set('brand', state.brand);
      if (state.sort !== 'recommended') p.set('sort', state.sort);
      var qs = p.toString();
      history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
    } catch (e) { /* 무시 */ }
  }

  /* ---------- API 호출: fetch → 실패하면 JSONP ---------- */
  function fetchJson(url) {
    return new Promise(function (resolve, reject) {
      var ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      var t = setTimeout(function () { if (ctl) ctl.abort(); reject(new Error('timeout')); }, TIMEOUT_MS);
      fetch(url, { credentials: 'omit', redirect: 'follow', signal: ctl ? ctl.signal : undefined })
        .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (d) { clearTimeout(t); resolve(d); })
        .catch(function (e) { clearTimeout(t); reject(e); });
    });
  }
  function jsonp(url) {
    return new Promise(function (resolve, reject) {
      var cb = 'ainsLibCb' + Date.now(), done = false, t, s = document.createElement('script');
      function finish() { done = true; clearTimeout(t); try { delete window[cb]; } catch (e) { window[cb] = undefined; } if (s.parentNode) s.parentNode.removeChild(s); }
      window[cb] = function (d) { if (done) return; finish(); resolve(d); };
      s.onerror = function () { if (done) return; finish(); reject(new Error('jsonp')); };
      t = setTimeout(function () { if (done) return; finish(); reject(new Error('timeout')); }, TIMEOUT_MS);
      s.src = url + '&callback=' + cb;
      document.head.appendChild(s);
    });
  }
  function fetchList() {
    var url = API_URL + '?action=list';
    return fetchJson(url).catch(function () { return jsonp(url); }).then(function (d) {
      if (!d || d.ok !== true || !Array.isArray(d.items)) throw new Error('bad response');
      return d.items;
    });
  }
  function pingDownload(id) {
    try {
      fetch(API_URL + '?action=hit&id=' + encodeURIComponent(id), { mode: 'no-cors', keepalive: true, credentials: 'omit' })
        .catch(function () {});
    } catch (e) { /* 집계 실패는 다운로드에 영향 없음 */ }
  }

  /* ---------- 캐시: 먼저 보여주고 뒤에서 갱신 ---------- */
  function readCache() {
    try {
      var c = JSON.parse(sessionStorage.getItem(CACHE_KEY) || 'null');
      return c && Array.isArray(c.items) ? c.items : null;
    } catch (e) { return null; }
  }
  function writeCache(items) {
    try { sessionStorage.setItem(CACHE_KEY, JSON.stringify({ t: Date.now(), items: items })); } catch (e) { /* 용량·차단 무시 */ }
  }

  /* ---------- 데이터 정리 ---------- */
  function prepare(raw) {
    return raw.map(function (it, i) {
      var tags = Array.isArray(it.tags) ? it.tags : [];
      var o = {
        id: str(it.id), title: str(it.title), category: str(it.category) || '기타', brand: str(it.brand),
        productLine: str(it.productLine), tags: tags.map(str), description: str(it.description),
        date: str(it.date), fileType: str(it.fileType), fileSize: str(it.fileSize),
        thumbnail: safeUrl(it.thumbnail, HTTPS), previewUrl: safeUrl(it.previewUrl, DRIVE),
        downloadUrl: safeUrl(it.downloadUrl, DRIVE), downloads: Number(it.downloads) || 0, _i: i
      };
      o._h = norm([o.title, o.category, o.brand, o.productLine, o.tags.join(' '), o.description, o.fileType].join(' '));
      return o;
    }).filter(function (o) { return o.id && o.downloadUrl; });
  }

  function categories() {
    var cnt = {}, out = [];
    state.items.forEach(function (it) { cnt[it.category] = (cnt[it.category] || 0) + 1; });
    CATEGORY_ORDER.forEach(function (c) { if (cnt[c]) out.push([c, cnt[c]]); });
    Object.keys(cnt).forEach(function (c) { if (CATEGORY_ORDER.indexOf(c) < 0) out.push([c, cnt[c]]); });
    return out;
  }
  function brands() {
    var cnt = {};
    state.items.forEach(function (it) { if (it.brand) cnt[it.brand] = (cnt[it.brand] || 0) + 1; });
    return Object.keys(cnt).map(function (b) { return [b, cnt[b]]; })
      .sort(function (a, b) { return (b[1] - a[1]) || (a[0] < b[0] ? -1 : 1); });
  }
  function visible() {
    var terms = norm(state.q).split(' ').filter(Boolean);
    var list = state.items.filter(function (it) {
      if (state.cat && it.category !== state.cat) return false;
      if (state.brand && it.brand !== state.brand) return false;
      for (var i = 0; i < terms.length; i++) if (it._h.indexOf(terms[i]) < 0) return false;
      return true;
    });
    if (state.sort === 'latest') {
      list.sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : (a.id < b.id ? 1 : -1); });
    } else if (state.sort === 'popular') {
      list.sort(function (a, b) { return (b.downloads - a.downloads) || (a.date < b.date ? 1 : a.date > b.date ? -1 : 0); });
    } else {
      list.sort(function (a, b) { return a._i - b._i; });   // 서버가 준 추천 순서
    }
    return list;
  }
  function filtersActive() { return !!(state.q || state.cat || state.brand); }

  /* ---------- 화면 뼈대 (한 번만 만듦) ---------- */
  function buildShell(app) {
    clear(app);

    ui.bar = el('form', { class: 'ains-lib__bar', role: 'search', 'aria-label': '자료 검색 및 필터' });
    ui.bar.addEventListener('submit', function (e) { e.preventDefault(); });

    var sw = el('div', { class: 'ains-lib__search' });
    sw.appendChild(el('label', { class: 'ains-lib__vh', for: 'ains-lib-q', text: '자료 검색' }));
    ui.q = el('input', {
      id: 'ains-lib-q', type: 'search', placeholder: '자료명, 브랜드, 제품군으로 검색',
      autocomplete: 'off', enterkeyhint: 'search', maxlength: '80'
    });
    ui.q.value = state.q;
    var timer;
    ui.q.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { state.q = ui.q.value; update(); }, 120);
    });
    sw.appendChild(ui.q);
    ui.bar.appendChild(sw);

    ui.chips = el('div', { class: 'ains-lib__chips', role: 'group', 'aria-label': '분류 필터' });
    ui.bar.appendChild(ui.chips);

    var sel = el('div', { class: 'ains-lib__selects' });
    ui.brand = el('select', { id: 'ains-lib-brand' });
    ui.brand.addEventListener('change', function () { state.brand = ui.brand.value; update(); });
    sel.appendChild(el('div', { class: 'ains-lib__field' }, [el('label', { for: 'ains-lib-brand', text: '브랜드' }), ui.brand]));
    ui.sort = el('select', { id: 'ains-lib-sort' });
    SORTS.forEach(function (s) { ui.sort.appendChild(el('option', { value: s[0], text: s[1] })); });
    ui.sort.value = state.sort;
    ui.sort.addEventListener('change', function () { state.sort = ui.sort.value; update(); });
    sel.appendChild(el('div', { class: 'ains-lib__field' }, [el('label', { for: 'ains-lib-sort', text: '정렬' }), ui.sort]));
    ui.bar.appendChild(sel);

    ui.count = el('span', { role: 'status', 'aria-live': 'polite' });
    ui.reset = el('button', { type: 'button', class: 'ains-lib__reset', text: '필터 초기화', hidden: '' });
    ui.reset.addEventListener('click', resetFilters);
    ui.metaRow = el('div', { class: 'ains-lib__meta-row' }, [ui.count, ui.reset]);

    ui.results = el('div', { class: 'ains-lib__results' });

    app.appendChild(ui.bar);
    app.appendChild(ui.metaRow);
    app.appendChild(ui.results);
    toolbarVisible(false);
  }
  function toolbarVisible(on) {
    ui.bar.hidden = !on;
    ui.metaRow.hidden = !on;
  }

  function renderChips() {
    // 칩을 다시 그리면 포커스가 사라지므로, 누르던 칩을 기억했다가 되돌려 준다 (키보드 사용자용)
    var active = document.activeElement, keep = null;
    if (active && active.parentNode === ui.chips) keep = active.getAttribute('data-cat');
    clear(ui.chips);
    var all = [['', '전체', state.items.length]].concat(categories().map(function (c) { return [c[0], c[0], c[1]]; }));
    all.forEach(function (c) {
      var b = el('button', { type: 'button', class: 'ains-lib__chip', 'data-cat': c[0], 'aria-pressed': String(state.cat === c[0]) }, [
        c[1], el('span', { class: 'ains-lib__n', text: String(c[2]), 'aria-hidden': 'true' })
      ]);
      b.setAttribute('aria-label', c[1] + ' ' + c[2] + '건');
      b.addEventListener('click', function () { state.cat = c[0]; update(); });
      ui.chips.appendChild(b);
      if (keep !== null && keep === c[0]) b.focus();
    });
  }
  function renderBrands() {
    clear(ui.brand);
    ui.brand.appendChild(el('option', { value: '', text: '전체 브랜드' }));
    brands().forEach(function (b) { ui.brand.appendChild(el('option', { value: b[0], text: b[0] + ' (' + b[1] + ')' })); });
    ui.brand.value = state.brand;
    if (ui.brand.value !== state.brand) state.brand = '';   // 사라진 브랜드가 URL에 남은 경우
  }

  /* ---------- 카드 ---------- */
  function thumbBlock(it) {
    var box = el('div', { class: 'ains-lib__thumb' });
    var ph = function () { return el('div', { class: 'ains-lib__ph', 'aria-hidden': 'true', text: (it.fileType || 'FILE').slice(0, 5) }); };
    if (it.thumbnail) {
      var img = el('img', {
        src: it.thumbnail, alt: it.title + ' 표지 미리보기', loading: 'lazy', decoding: 'async',
        referrerpolicy: 'no-referrer', width: '640', height: '480'
      });
      img.addEventListener('error', function () { if (img.parentNode) img.parentNode.replaceChild(ph(), img); });
      box.appendChild(img);
    } else {
      box.appendChild(ph());
    }
    return box;
  }
  function facts(it) {
    var ul = el('ul', { class: 'ains-lib__facts' });
    var line = function (parts) {
      parts = parts.filter(Boolean);
      if (!parts.length) return;
      var li = el('li');
      parts.forEach(function (p, i) {
        if (i) li.appendChild(el('span', { class: 'sep', 'aria-hidden': 'true', text: '·' }));
        li.appendChild(document.createTextNode(p));
      });
      ul.appendChild(li);
    };
    line([it.brand, it.date ? it.date + ' 등록' : '']);
    line([it.fileType, it.fileSize]);
    return ul;
  }
  function card(it) {
    var meta = [it.fileType, it.fileSize].filter(Boolean).join(' · ');
    var dl = el('a', {
      class: 'ains-lib__btn ains-lib__btn--main', href: it.downloadUrl, rel: 'noopener',
      'aria-label': it.title + ' 다운로드' + (meta ? ' (' + meta + ')' : ''), text: '다운로드'
    });
    dl.addEventListener('click', function () { pingDownload(it.id); it.downloads += 1; writeCache(state.items.map(strip)); });
    var actions = el('div', { class: 'ains-lib__actions' }, [dl]);
    if (it.previewUrl) {
      actions.appendChild(el('a', {
        class: 'ains-lib__btn', href: it.previewUrl, target: '_blank', rel: 'noopener noreferrer',
        'aria-label': it.title + ' 미리보기 (새 창)', text: '미리보기'
      }));
    }
    var body = el('div', { class: 'ains-lib__body' }, [
      el('p', { class: 'ains-lib__cat', text: it.category }),
      el('h3', { class: 'ains-lib__name', text: it.title }),
      facts(it),
      it.description ? el('p', { class: 'ains-lib__desc', text: it.description }) : null,
      actions
    ]);
    var art = el('article', { class: 'ains-lib__card', id: 'ains-' + it.id, tabindex: '-1' }, [thumbBlock(it), body]);
    return el('li', null, [art]);
  }
  function strip(it) {   // 캐시에 넣을 때 화면용 필드 제거
    return { id: it.id, title: it.title, category: it.category, brand: it.brand, productLine: it.productLine,
      tags: it.tags, description: it.description, date: it.date, fileType: it.fileType, fileSize: it.fileSize,
      thumbnail: it.thumbnail, previewUrl: it.previewUrl, downloadUrl: it.downloadUrl, downloads: it.downloads };
  }

  /* ---------- 상태 화면 ---------- */
  function showSkeleton() {
    clear(ui.results);
    var ul = el('ul', { class: 'ains-lib__grid', 'aria-hidden': 'true' });
    for (var i = 0; i < SKELETON_COUNT; i++) {
      ul.appendChild(el('li', null, [el('div', { class: 'ains-lib__card ains-lib__sk' }, [
        el('div', { class: 'ains-lib__thumb' }),
        el('div', { class: 'ains-lib__body' }, [
          el('div', { class: 'ains-lib__line ains-lib__line--s' }),
          el('div', { class: 'ains-lib__line ains-lib__line--l' }),
          el('div', { class: 'ains-lib__line' })
        ])
      ])]));
    }
    ui.results.appendChild(el('span', { class: 'ains-lib__vh', role: 'status', text: '자료 목록을 불러오는 중입니다.' }));
    ui.results.appendChild(ul);
  }
  function showState(kind, title, text, btnLabel, onClick) {
    clear(ui.results);
    var box = el('div', { class: 'ains-lib__state' + (kind === 'error' ? ' ains-lib__state--error' : ''), role: kind === 'error' ? 'alert' : 'status' }, [
      el('h2', { text: title }), el('p', { text: text })
    ]);
    if (btnLabel) {
      var b = el('button', { type: 'button', class: 'ains-lib__btn', text: btnLabel });
      b.addEventListener('click', onClick);
      box.appendChild(b);
    }
    ui.results.appendChild(box);
  }
  function showError() {
    toolbarVisible(false);
    showState('error', '자료를 불러오지 못했습니다',
      '네트워크 상태를 확인하시고 다시 시도해 주세요. 문제가 계속되면 잠시 후 다시 방문해 주세요.',
      '다시 시도', function () { load(); });
  }

  /* ---------- 갱신 ---------- */
  function resetFilters() {
    state.q = ''; state.cat = ''; state.brand = ''; ui.q.value = '';
    update();
  }
  function update() {
    if (!state.loaded) return;
    renderChips();
    renderBrands();
    var list = visible(), total = state.items.length;
    writeQuery();
    ui.reset.hidden = !filtersActive();
    ui.count.textContent = filtersActive() ? list.length + '건 (전체 ' + total + '건)' : '총 ' + total + '건';

    if (!total) {
      toolbarVisible(false);
      showState('empty', '아직 등록된 자료가 없습니다', '새 자료가 등록되면 이곳에 표시됩니다.');
      return;
    }
    toolbarVisible(true);
    if (!list.length) {
      showState('empty', '조건에 맞는 자료가 없습니다', '검색어를 줄이거나 분류·브랜드 필터를 바꿔 보세요.', '필터 초기화', resetFilters);
      return;
    }
    clear(ui.results);
    var ul = el('ul', { class: 'ains-lib__grid' });
    list.forEach(function (it) { ul.appendChild(card(it)); });
    ui.results.appendChild(ul);
  }

  function focusTarget() {
    var id = '';
    try { id = decodeURIComponent((location.hash || '').replace(/^#/, '')); } catch (e) { return; }
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(id)) return;
    var n = document.getElementById('ains-' + id);
    if (!n) return;
    n.classList.add('is-target');
    n.scrollIntoView({ block: 'center' });
    n.focus({ preventScroll: true });
  }

  /* ---------- 불러오기 ---------- */
  var firstRender = true;
  function apply(items) {
    state.items = prepare(items);
    state.loaded = true;
    update();
    if (firstRender) { firstRender = false; focusTarget(); }
  }
  function load() {
    var cached = readCache();
    if (cached) apply(cached); else { toolbarVisible(false); showSkeleton(); }
    fetchList().then(function (items) {
      writeCache(items);
      apply(items);
    }).catch(function () {
      if (!state.loaded) showError();   // 캐시로 이미 보여 주는 중이면 조용히 유지
    });
  }

  /* ---------- 사이트 공통 메뉴·화면 모드 (www 전용, 요소가 없으면 건너뜀) ---------- */
  function initChrome() {
    var nav = document.getElementById('nav'), btn = document.getElementById('menuBtn');
    if (nav && btn) {
      var set = function (o) {
        nav.classList.toggle('open', o);
        btn.setAttribute('aria-expanded', String(o));
        btn.setAttribute('aria-label', o ? '메뉴 닫기' : '메뉴 열기');
      };
      btn.addEventListener('click', function (e) { e.stopPropagation(); set(!nav.classList.contains('open')); });
      Array.prototype.forEach.call(document.querySelectorAll('#menu a'), function (a) { a.addEventListener('click', function () { set(false); }); });
      document.addEventListener('click', function (e) { if (nav.classList.contains('open') && !nav.contains(e.target)) set(false); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && nav.classList.contains('open')) { set(false); btn.focus(); } });
    }
    var tb = document.getElementById('themeBtn');
    if (tb) tb.addEventListener('click', function () {
      var r = document.documentElement;
      var cur = r.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = cur === 'dark' ? 'light' : 'dark';
      r.setAttribute('data-theme', next);
      try { localStorage.setItem('ains_theme', next); } catch (e) { /* 무시 */ }
    });
  }

  function init() {
    initChrome();
    var app = document.getElementById('ains-lib-app');
    if (!app) return;
    readQuery();
    buildShell(app);
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
