/* news.ainsonic.com 보강 스크립트 — 기존 스크립트를 바꾸지 않고 위에 얹는다.
   1) 키보드로 카드·표 행을 열고 닫기  2) 렌더링 결과 안전 점검(기존 코드가 놓친 위험 제거)  3) 본문 건너뛰기 링크 */
(function () {
  'use strict';

  /* ---- 3) 본문 건너뛰기 ---- */
  var main = document.querySelector('main');
  if (main && !main.id) main.id = 'main';
  if (main) {
    var skip = document.createElement('a');
    skip.className = 'np-skip'; skip.href = '#main'; skip.textContent = '본문으로 건너뛰기';
    document.body.insertBefore(skip, document.body.firstChild);
  }

  /* ---- 2) 안전 점검: 동적으로 만들어진 노드에서 실행 가능한 코드를 제거 ----
     기존 코드는 소식 데이터를 HTML 문자열에 그대로 끼워 넣는다(이스케이프 없음).
     데이터에 악성 마크업이 섞여도 실행되지 않도록 허용 목록 밖의 것을 지운다.
     근본 해결은 원본 생성 코드에서 이스케이프하는 것이며, 이 단계는 보조 방어선이다. */
  var ALLOWED_HANDLERS = [
    /^handleRowClick\('row-\d+',\s*'expand-\d+'\)$/,
    /^handleCardClick\(\d+\)$/,
    /^event\.stopPropagation\(\)$/,
    /^thumbFallback\(this\)$/,
    /^this\.parentNode\.remove\(\)$/
  ];
  var BAD_TAGS = 'script,iframe,object,embed,link,meta,base,form,style,svg script';
  function safeUrl(v) { return /^\s*(https?:|mailto:|tel:|\/|#|n\/|rss\.xml|[\w.-]+\.html)/i.test(v) && !/^\s*javascript:/i.test(v); }

  function sanitize(root) {
    if (!root || root.nodeType !== 1) return;
    var nodes = [root].concat(Array.prototype.slice.call(root.querySelectorAll('*')));
    nodes.forEach(function (n) {
      if (n.matches && n.matches(BAD_TAGS)) { n.remove(); return; }
      Array.prototype.slice.call(n.attributes).forEach(function (a) {
        var name = a.name.toLowerCase();
        if (name.indexOf('on') === 0) {
          var ok = ALLOWED_HANDLERS.some(function (re) { return re.test(a.value.trim()); });
          if (!ok) n.removeAttribute(a.name);
        } else if ((name === 'href' || name === 'src' || name === 'xlink:href' || name === 'srcset' || name === 'action' || name === 'formaction') && !safeUrl(a.value)) {
          n.removeAttribute(a.name);
        } else if (name === 'style' && /expression\(|url\(\s*['"]?\s*javascript:/i.test(a.value)) {
          n.removeAttribute(a.name);
        }
      });
    });
  }

  /* ---- 1) 키보드 조작 ---- */
  function enhance(el, controlsId) {
    if (el.getAttribute('data-np') === '1') return;
    el.setAttribute('data-np', '1');
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    el.setAttribute('aria-expanded', String(el.classList.contains('active') || el.classList.contains('expanded')));
    if (controlsId) el.setAttribute('aria-controls', controlsId);
  }
  function syncExpanded(el) {
    el.setAttribute('aria-expanded', String(el.classList.contains('active') || el.classList.contains('expanded')));
  }
  function enhanceAll(container) {
    Array.prototype.forEach.call(container.querySelectorAll('tr.main-row'), function (row) {
      var m = /handleRowClick\('[^']+',\s*'([^']+)'\)/.exec(row.getAttribute('onclick') || '');
      enhance(row, m && m[1]);
    });
    Array.prototype.forEach.call(container.querySelectorAll('.news-card'), function (c) { enhance(c); });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var t = e.target;
    if (!t || !t.matches || !t.matches('tr.main-row[data-np], .news-card[data-np]')) return; // 안쪽 링크·버튼은 그대로 동작
    e.preventDefault();
    t.click();
    setTimeout(function () { syncExpanded(t); }, 0);
  });
  document.addEventListener('click', function () {
    setTimeout(function () {
      Array.prototype.forEach.call(document.querySelectorAll('[data-np="1"]'), syncExpanded);
    }, 0);
  });

  var targets = ['newsTableBody', 'featuredGrid', 'noticePanelBody', 'trendBrands'].map(function (id) { return document.getElementById(id); }).filter(Boolean);
  var obs = new MutationObserver(function (muts) {
    var touched = [];
    muts.forEach(function (m) {
      Array.prototype.forEach.call(m.addedNodes, function (n) { sanitize(n); });
      if (touched.indexOf(m.target) < 0) touched.push(m.target);
    });
    touched.forEach(function (t) { var host = t.closest ? t.closest('tbody,#featuredGrid') || t : t; if (host.querySelectorAll) enhanceAll(host); });
  });
  targets.forEach(function (t) { sanitize(t); enhanceAll(t); obs.observe(t, { childList: true, subtree: true }); });
})();
