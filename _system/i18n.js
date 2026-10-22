/* XLRTE i18n: shows the German UI in English (or keeps German). Data-driven, no build step, works offline.
   window.XLRTE_I18N = {map: {"German segment {0}": "English segment {0}"}, words: {"Tage": "days"}}; window.XLRTE_LANG = "de" | "en".
   The viewer's own choice (toggle bottom left) wins and is remembered in this browser. Text the catalogue does not know stays German. */
(function () {
  var D = window.XLRTE_I18N || {}, lang = null;
  try { lang = localStorage.getItem("xlrte.lang"); } catch (e) { /* storage blocked */ }
  lang = lang || window.XLRTE_LANG || "de";
  function toggle() {
    var b = document.createElement("button");
    b.textContent = lang === "en" ? "Deutsch" : "English";
    b.setAttribute("aria-label", lang === "en" ? "Auf Deutsch umschalten" : "Switch to English");
    b.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:9999;font:12px/1 system-ui,sans-serif;padding:7px 10px;border-radius:999px;border:1px solid rgba(127,127,127,.4);background:rgba(127,127,127,.12);color:inherit;cursor:pointer";
    b.onclick = function () { try { localStorage.setItem("xlrte.lang", lang === "en" ? "de" : "en"); } catch (e) {} location.reload(); };
    document.body.appendChild(b);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", toggle); else toggle();
  if (lang !== "en") return;
  document.documentElement.lang = "en";
  var exact = {}, pats = [], words = D.words || {};
  Object.keys(D.map || {}).forEach(function (k) {
    var v = D.map[k];
    if (/\{\d+\}/.test(k)) {
      var idx = [];
      var re = "^" + k.replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace(/\{(\d+)\}/g, function (_, n) { idx.push(+n); return "([\\s\\S]*?)"; }) + "$";
      try { pats.push([new RegExp(re), idx, v, k.replace(/\{\d+\}/g, "").length]); } catch (e) { /* skip */ }
    } else exact[k] = v;
  });
  pats.sort(function (a, b) { return b[3] - a[3]; });
  var WORD = /[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-]*/g;
  function tr(t) {
    var s = t.replace(/\s+/g, " ").trim();
    if (!s || !/[A-Za-zÄÖÜäöü]/.test(s)) return t;
    var out = exact[s];
    if (out === undefined) {
      for (var i = 0; i < pats.length; i++) {
        var m = pats[i][0].exec(s);
        if (m) { var idx = pats[i][1]; out = pats[i][2].replace(/\{(\d+)\}/g, function (_, n) { var j = idx.indexOf(+n); return j >= 0 ? tr(m[j + 1]) : ""; }); break; }
      }
    }
    if (out === undefined && (s.match(WORD) || []).length <= 3) {   // word fallback only for short labels ("54 Tage"), never sentences
      var hit = false, w = s.replace(WORD, function (x) { if (words[x] !== undefined) { hit = true; return words[x]; } return x; });
      if (hit) out = w;
    }
    if (out === undefined || out === s) return t;
    var lead = t.match(/^\s*/)[0], tail = t.match(/\s*$/)[0];
    return lead + out + tail;
  }
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, CODE: 1, PRE: 1, NOSCRIPT: 1 };
  var ATTR = ["placeholder", "title", "data-tip", "aria-label"];
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { var p = root.parentNode; if (p && !SKIP[p.nodeName]) { var v = tr(root.nodeValue); if (v !== root.nodeValue) root.nodeValue = v; } return; }
    if (root.nodeType !== 1 || SKIP[root.nodeName] || (root.closest && root.closest("[data-no-i18n]"))) return;
    ATTR.forEach(function (a) { var x = root.getAttribute(a); if (x) { var y = tr(x); if (y !== x) root.setAttribute(a, y); } });
    for (var c = root.firstChild; c; c = c.nextSibling) walk(c);
  }
  function start() {
    walk(document.body);
    if (document.title) document.title = tr(document.title);
    new MutationObserver(function (ms) {
      ms.forEach(function (m) {
        if (m.type === "characterData") walk(m.target);
        else if (m.type === "attributes") walk(m.target);
        else m.addedNodes.forEach(walk);
      });
    }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTR });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
