/* ============================================================
   Shared runtime for all Job Search views (Executive Edition 2026).
   Data is embedded as strict JSON in <script type="application/json" id="DATA">.
   Strict JSON ensures data integrity with loud validation.
   ============================================================ */

const JS26 = (() => {
  const TODAY = new Date(document.documentElement.dataset.today + "T00:00:00Z");
  const STAGES = ["Watchlist", "Applied", "Screening", "Interviewing", "Final", "Closed"];
  const OPEN = STAGES.slice(0, 5);

  /* Diacritic-folded normalization for instant, forgiving search */
  function norm(str) {
    return String(str ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function load() {
    const el = document.getElementById("DATA");
    let d;
    try {
      d = JSON.parse(el.textContent);
    } catch (e) {
      const b = document.createElement("div");
      b.className = "err";
      b.textContent = "DATA PARSE ERROR — das Dashboard kann die Pipeline nicht laden: " + e.message;
      const wrap = document.querySelector(".wrap") || document.body;
      wrap.prepend(b);
      throw e;
    }
    if (!Array.isArray(d.rows) || d.rows.length < d.expect_rows) {
      const b = document.createElement("div");
      b.className = "err";
      b.textContent = `ROW COUNT MISMATCH — erwartet wurden ${d.expect_rows} Zeilen, geladen wurden ${(d.rows || []).length}. Die Datenbasis ist unvollständig.`;
      const wrap = document.querySelector(".wrap") || document.body;
      wrap.prepend(b);
    }
    d.rows.forEach(r => {
      r._idle = (r.days_idle === "" || r.days_idle == null) ? null : +r.days_idle;
      r.score = +r.score || 0;
      r._norm = norm(r.company + " " + r.role + " " + r.note + " " + (r.contacts || "") + " " + (r.uid || "") + " " + (r.lane || ""));
    });
    return d;
  }

  const days = iso => iso ? Math.round((TODAY - new Date(iso + "T00:00:00Z")) / 864e5) : null;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
  const de = iso => iso ? iso.slice(8, 10) + "." + iso.slice(5, 7) + "." + iso.slice(0, 4) : "—";
  const pill = s => `<span class="pill st-${esc(s)}">${esc(s)}</span>`;

  const heatClass = v => v >= 80 ? "score-heat-4" : v >= 60 ? "score-heat-3" : v >= 40 ? "score-heat-2" : v >= 20 ? "score-heat-1" : "score-heat-0";
  const heat = v => `var(--heat-${v >= 80 ? 4 : v >= 60 ? 3 : v >= 40 ? 2 : v >= 20 ? 1 : 0})`;
  const scoreBadge = (score, stage) => stage === "Closed"
    ? `<span style="color:var(--muted)">—</span>`
    : `<span class="score-badge ${heatClass(score)}">${score}</span>`;

  const folder = r => r.folder_id
    ? `<a href="https://drive.google.com/drive/folders/${esc(r.folder_id)}" target="_blank" rel="noopener" class="folder-link" title="Drive-Ordner öffnen" onclick="event.stopPropagation()">Ordner ↗</a>`
    : `<span style="color:var(--muted)">—</span>`;

  /* Health status derived from idle days */
  function health(r) {
    if (r.stage === "Closed") return { k: "closed", l: "—", cls: "closed" };
    if (r._idle == null)      return { k: "unknown", l: "kein Datum", cls: "cooling" };
    if (r._idle <= 7)         return { k: "hot", l: r._idle + "d", cls: "hot" };
    if (r._idle <= 21)        return { k: "warm", l: r._idle + "d", cls: "warm" };
    if (r._idle <= 45)        return { k: "cooling", l: r._idle + "d", cls: "cooling" };
    return { k: "stale", l: r._idle + "d", cls: "stale" };
  }

  const healthDot = h => `<span class="health-dot ${h.cls}" title="Signal vor ${h.l}"></span>`;

  const prioBadge = (level, text) => {
    const k = level || "normal";
    const defaultLabels = {
      urgent: "🚨 Dringend",
      high: "⚡ Prio 1",
      warm: "💬 Warm-Touch",
      normal: "📅 Geplant"
    };
    return `<span class="badge-prio ${esc(k)}">${esc(text || defaultLabels[k] || "Geplant")}</span>`;
  };

  /* Table multi-column sorting */
  function sortable(table, rerender) {
    let k = null, dir = -1;
    table.querySelectorAll("th[data-k]").forEach(th => {
      th.addEventListener("click", () => {
        const nk = th.dataset.k;
        dir = (k === nk) ? -dir : (th.dataset.dir === "asc" ? 1 : -1);
        k = nk;
        table.querySelectorAll("th[data-k]").forEach(a => {
          a.classList.remove("sorted-asc", "sorted-desc");
          const ar = a.querySelector(".ar");
          if (ar) ar.textContent = "";
        });
        th.classList.add(dir > 0 ? "sorted-asc" : "sorted-desc");
        const ar = th.querySelector(".ar");
        if (ar) ar.textContent = dir > 0 ? "▲" : "▼";

        rerender((a, b) => {
          let x = a[k], y = b[k];
          if (typeof x === "number" || typeof y === "number") {
            x = +x || 0; y = +y || 0;
          } else {
            x = String(x ?? "").toLowerCase();
            y = String(y ?? "").toLowerCase();
          }
          return x < y ? -dir : x > y ? dir : 0;
        });
      });
    });
  }

  /* Safe LocalStorage wrapper */
  const store = key => ({
    get() {
      try { return JSON.parse(localStorage.getItem(key) || "{}"); }
      catch (e) { return {}; }
    },
    set(v) {
      try { localStorage.setItem(key, JSON.stringify(v)); }
      catch (e) {}
    }
  });

  /* CSS Variable helper */
  function css(v) {
    return getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  }

  const PALETTE = () => [
    css("--w-applied"), css("--w-screening"), css("--w-interviewing"),
    css("--w-final"), css("--w-watchlist"), css("--w-closed")
  ];

  /* Interactive Opportunity Detail Drawer */
  function initDrawer() {
    if (document.getElementById("drawer-backdrop")) return;
    const backdrop = document.createElement("div");
    backdrop.id = "drawer-backdrop";
    backdrop.className = "drawer-backdrop";

    const drawer = document.createElement("div");
    drawer.id = "detail-drawer";
    drawer.className = "detail-drawer";
    drawer.innerHTML = `
      <div class="drawer-header">
        <div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span id="dr-stage"></span>
            <span id="dr-score"></span>
          </div>
          <h3 class="drawer-title" id="dr-company"></h3>
          <div class="drawer-subtitle" id="dr-role"></div>
        </div>
        <button class="drawer-close" id="dr-close" title="Schließen (Esc)">&times;</button>
      </div>
      <div class="drawer-body">
        <div class="drawer-section">
          <div class="drawer-section-title">Eckdaten</div>
          <div class="drawer-meta-grid">
            <div class="drawer-meta-item">
              <div class="drawer-meta-label">UID / Kennung</div>
              <div class="drawer-meta-value" id="dr-uid">—</div>
            </div>
            <div class="drawer-meta-item">
              <div class="drawer-meta-label">Lane / Bereich</div>
              <div class="drawer-meta-value" id="dr-lane">—</div>
            </div>
            <div class="drawer-meta-item">
              <div class="drawer-meta-label">Bewerbung eingereicht</div>
              <div class="drawer-meta-value" id="dr-applied">—</div>
            </div>
            <div class="drawer-meta-item">
              <div class="drawer-meta-label">Letztes Signal / Stillstand</div>
              <div class="drawer-meta-value" id="dr-idle">—</div>
            </div>
            <div class="drawer-meta-item">
              <div class="drawer-meta-label">Gehaltspositionierung</div>
              <div class="drawer-meta-value" id="dr-salary">—</div>
            </div>
            <div class="drawer-meta-item">
              <div class="drawer-meta-label">Drive Nachweis-Ordner</div>
              <div class="drawer-meta-value" id="dr-folder">—</div>
            </div>
          </div>
        </div>
        <div class="drawer-section" id="dr-act-sec">
          <div class="drawer-section-title">Nächster Schritt</div>
          <div class="drawer-meta-item" style="background:var(--warn-tint);border-color:color-mix(in srgb, var(--warn) 30%, transparent)">
            <div style="font-weight:700;color:var(--warn);font-size:11px" id="dr-due">Fällig: —</div>
            <div style="font-weight:600;color:var(--ink);margin-top:2px" id="dr-action">—</div>
          </div>
        </div>
        <div class="drawer-section">
          <div class="drawer-section-title">Kontakte & Panel</div>
          <div style="font-size:12.5px;color:var(--ink-2)" id="dr-contacts">—</div>
        </div>
        <div class="drawer-section">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <div class="drawer-section-title" style="margin-bottom:0">Letzter Verlauf / Notiz</div>
            <button class="chip" id="dr-copy-note" style="padding:2px 8px;font-size:10.5px">Kopieren</button>
          </div>
          <div class="drawer-note-box" id="dr-note"></div>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);
    document.body.appendChild(drawer);

    const close = () => {
      backdrop.classList.remove("open");
      drawer.classList.remove("open");
      document.querySelectorAll("tbody tr.selected").forEach(tr => tr.classList.remove("selected"));
    };

    backdrop.addEventListener("click", close);
    document.getElementById("dr-close").addEventListener("click", close);
    document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });

    document.getElementById("dr-copy-note").addEventListener("click", () => {
      const text = document.getElementById("dr-note").textContent;
      navigator.clipboard?.writeText(text).then(() => {
        const btn = document.getElementById("dr-copy-note");
        btn.textContent = "Kopiert!";
        setTimeout(() => { btn.textContent = "Kopieren"; }, 1500);
      });
    });
  }

  function openDrawer(r, trEl) {
    initDrawer();
    const h = health(r);
    const sal = {
      above: '<span style="color:var(--ok)">über Zielband ✓</span>',
      around: '<span style="color:var(--warn)">um Zielband ~</span>',
      below: '<span style="color:var(--bad)">unter Zielband ✗</span>'
    }[r.salary_fit] || '<span style="color:var(--muted)">nicht verhandelt / unbestimmt</span>';

    document.getElementById("dr-stage").innerHTML = pill(r.stage);
    document.getElementById("dr-score").innerHTML = scoreBadge(r.score, r.stage);
    document.getElementById("dr-company").textContent = r.company || "—";
    document.getElementById("dr-role").textContent = r.role || "—";
    document.getElementById("dr-uid").textContent = r.uid ? "UID " + r.uid : "—";
    document.getElementById("dr-lane").textContent = r.lane || "—";
    document.getElementById("dr-applied").textContent = de(r.applied);
    document.getElementById("dr-idle").innerHTML = `${healthDot(h)} vor ${h.l} (${de(r.last_event)})`;
    document.getElementById("dr-salary").innerHTML = sal;
    document.getElementById("dr-folder").innerHTML = r.folder_id
      ? `<a href="https://drive.google.com/drive/folders/${esc(r.folder_id)}" target="_blank" rel="noopener">Drive-Ordner ${esc(r.uid || "")} öffnen ↗</a>`
      : `<span style="color:var(--muted)">kein Ordner hinterlegt</span>`;

    const actSec = document.getElementById("dr-act-sec");
    if (r.next_action) {
      actSec.style.display = "";
      document.getElementById("dr-due").textContent = r.due ? `Fällig: ${de(r.due)}` : "Frist: offen";
      document.getElementById("dr-action").textContent = r.next_action;
    } else {
      actSec.style.display = "none";
    }

    document.getElementById("dr-contacts").textContent = r.contacts || "Keine namentlichen Kontakte erfasst.";
    document.getElementById("dr-note").textContent = r.note || "Keine Notizen erfasst.";

    document.querySelectorAll("tbody tr.selected").forEach(tr => tr.classList.remove("selected"));
    if (trEl) trEl.classList.add("selected");

    document.getElementById("drawer-backdrop").classList.add("open");
    document.getElementById("detail-drawer").classList.add("open");
  }

  /* Theme Switcher Toggle */
  function initTheme() {
    const key = "js26_theme";
    const current = localStorage.getItem(key) || "auto";
    if (current !== "auto") {
      document.documentElement.setAttribute("data-theme", current);
    }
    const updateBtn = () => {
      const btn = document.getElementById("theme-toggle");
      if (!btn) return;
      const theme = document.documentElement.getAttribute("data-theme") || "auto";
      btn.innerHTML = theme === "dark" ? "🌙 Dunkel" : theme === "light" ? "☀️ Hell" : "💻 Auto";
    };
    updateBtn();
    document.addEventListener("click", e => {
      const btn = e.target.closest("#theme-toggle");
      if (!btn) return;
      const t = document.documentElement.getAttribute("data-theme") || "auto";
      const next = t === "auto" ? "light" : t === "light" ? "dark" : "auto";
      if (next === "auto") {
        document.documentElement.removeAttribute("data-theme");
        localStorage.removeItem(key);
      } else {
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem(key, next);
      }
      updateBtn();
    });
  }

  /* Safe Fallback Charting System (Offline / CDN Independent) */
  function chart(fn, canvasId, fallbackRenderer) {
    try {
      if (typeof Chart === "undefined") throw new Error("Chart.js nicht geladen (Offline-Modus)");
      return fn();
    } catch (e) {
      const c = document.getElementById(canvasId);
      if (!c || !c.parentElement) return null;
      if (typeof fallbackRenderer === "function") {
        c.parentElement.innerHTML = fallbackRenderer();
      } else {
        c.parentElement.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:center;height:100%;padding:14px">
            <div style="color:var(--muted);font-size:11.5px;text-align:center;line-height:1.6">
              <b>Diagramm (Offline)</b><br>
              <span style="opacity:.8">${esc(e.message)}</span>
            </div>
          </div>`;
      }
      return null;
    }
  }

  /* Pure SVG & CSS Funnel / Bar Fallback Renderers */
  function renderSvgFunnel(stages, counts, colors) {
    const maxVal = Math.max(...counts, 1);
    const rows = stages.map((s, idx) => {
      const c = counts[idx] || 0;
      const pct = Math.round((c / maxVal) * 100);
      const col = colors[idx] || "var(--brand-2)";
      return `
        <div class="svg-funnel-row">
          <div class="svg-funnel-label">${esc(s)}</div>
          <div class="svg-funnel-track">
            <div class="svg-funnel-fill" style="width:${Math.max(pct, 6)}%;background:${col}">
              ${pct > 18 ? pct + "%" : ""}
            </div>
          </div>
          <div class="svg-funnel-count">${c}</div>
        </div>`;
    }).join("");
    return `<div class="svg-funnel">${rows}</div>`;
  }

  function donut(ctx, labels, data, colors) {
    return new Chart(ctx, {
      type: "doughnut",
      data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
      options: {
        cutout: "64%",
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 10, boxHeight: 10, font: { size: 11 }, color: css("--ink-2"), padding: 10 }
          }
        },
        maintainAspectRatio: false
      }
    });
  }

  function bars(ctx, labels, data, color, horizontal) {
    return new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{ data, backgroundColor: color, borderRadius: 4, maxBarThickness: 32 }]
      },
      options: {
        indexAxis: horizontal ? "y" : "x",
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: !horizontal, color: css("--line-2") },
            ticks: { color: css("--muted"), font: { size: 10.5 } }
          },
          y: {
            grid: { display: horizontal ? false : true, color: css("--line-2") },
            beginAtZero: true,
            ticks: { color: css("--muted"), font: { size: 10.5 }, precision: 0 }
          }
        },
        maintainAspectRatio: false
      }
    });
  }

  // Auto-init theme when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { initTheme(); initDrawer(); });
  } else {
    initTheme();
    initDrawer();
  }

  /* Intel tab of a briefing card: the files intel_index.json found for one uid */
  const INTEL_LABEL = { cheat_sheet: "Cheat Sheet", briefing: "Briefing", cockpit: "Cockpit", jd_intel: "JD-Intel", prep_brief: "Prep-Brief", strategy: "Strategy-Dokument" };
  const intelKey = u => { const s = String(u == null ? "" : u).trim(); return /^\d+$/.test(s) ? String(parseInt(s, 10)) : s; };
  const intelCount = e => ((e && e.items) || []).filter(i => !i.superseded).length;
  const intelHref = i => i.link || encodeURI(i.path || "").replace(/#/g, "%23").replace(/\?/g, "%3F");
  function intelHtml(e) {
    if (!e) return `<div class="intel-empty">Kein Intel-Index für dieses Verfahren (intel_index.py nicht gelaufen).</div>`;
    const warn = (e.warnings || []).map(w => `<div class="intel-warn">⚠ ${esc(w)}</div>`).join("");
    const items = e.items || [];
    if (!items.length) return warn + `<div class="intel-empty">Noch kein Cheat Sheet oder Briefing im Ordner gefunden.</div>`;
    const row = i => `<li class="intel-item${i.superseded ? " old" : ""}"><span class="intel-kind">${esc(INTEL_LABEL[i.kind] || i.kind)}</span>` +
      `<a href="${esc(intelHref(i))}" target="_blank" rel="noopener">${esc(i.name)}</a>` +
      `<span class="intel-meta">${esc(i.where || "Arbeitgeber-Ordner")} · ${de(i.modified)}${i.superseded ? " · ältere Fassung" : ""}</span></li>`;
    return warn + `<ul class="intel-list">${items.map(row).join("")}</ul>`;
  }

  /* Conversation cockpit of one uid (Cockpit_<Firma>_…html, written by prep_engine --from-content): the newest current one, or null.
     The owner's own cockpit PDFs ("Nordberatung_Cockpit_…") are not it. The path is relative to the career folder, like every intel link. */
  function cockpitLink(uid, idx) {
    const e = idx && idx.uids && idx.uids[intelKey(uid)];
    const hits = ((e && e.items) || []).filter(i => i.kind === "cockpit" && !i.superseded && /^Cockpit_/i.test(i.name || "") && /\.html?$/i.test(i.name || ""));
    if (!hits.length) return null;
    hits.sort((a, b) => String(b.modified || "").localeCompare(String(a.modified || "")));
    return { href: intelHref(hits[0]), name: hits[0].name, modified: hits[0].modified || "" };
  }

  /* When the index was made; a list more than 2 days old is flagged, so a stale cheat-sheet list is never mistaken for current */
  const intelStamp = idx => {
    if (!idx || !idx.generated) return "";
    const day = idx.generated.slice(0, 10);
    const old = (days(day) || 0) > 2;
    return `<div class="intel-stamp${old ? " stale" : ""}">Index vom ${de(day)}${old ? " — veraltet, intel_index.py neu laufen lassen" : ""}</div>`;
  };

  /* Reading pane (Briefings page): the live positions that have documents, and one document at a time.
     The html of a markdown document comes from md_safe.py (escaped server side); everything else is escaped here. */
  const READER_STAGES = [["Final", "Endrunde"], ["Interviewing", "Gespräche"], ["Screening", "Screening"], ["Applied", "Beworben"]];
  function readerGroups(rows, reader) {
    const R = reader || {};
    return READER_STAGES.map(([stage, label]) => {
      const items = (rows || []).filter(r => r.stage === stage && R[intelKey(r.uid)] && (R[intelKey(r.uid)].docs || []).length)
        .map(r => ({ r, key: intelKey(r.uid), entry: R[intelKey(r.uid)] }))
        .sort((a, b) => (Number(b.r.score) || 0) - (Number(a.r.score) || 0));
      return { stage, label, items };
    }).filter(g => g.items.length);
  }
  function readerQualityHtml(q) {
    if (!q || typeof q !== "object") return "";
    const chip = (cls, text, title) => `<span class="qchip${cls ? " " + cls : ""}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;
    const lint = { pass: ["ok", "Lint bestanden"], warn: ["warn", "Lint: Warnung"], fail: ["fail", "Lint: Fehler"] }[q.lint] || ["warn", "Lint unbekannt"];
    const out = [chip(lint[0], lint[1], (q.lint_rules || []).join(", ")), chip("", `${Number(q.facts) || 0} Fakten · ${Number(q.inferences) || 0} Schlüsse`)];
    if (Number(q.facts_unsourced)) out.push(chip("warn", `${Number(q.facts_unsourced)} Fakten ohne Quelle`));
    out.push(chip(Number(q.domains) >= 2 ? "" : "warn", `${Number(q.sources) || 0} Quellen · ${Number(q.domains) || 0} Domänen`));
    if (q.oldest_source_age != null) out.push(chip(Number(q.oldest_source_age) > 14 ? "warn" : "", `älteste Quelle ${Number(q.oldest_source_age)} Tage`));
    if (Number(q.unverified)) out.push(chip("warn", `${Number(q.unverified)} nicht verifiziert`));
    if (q.open_section === false) out.push(chip("warn", "Abschnitt „Offen“ fehlt"));
    if (Array.isArray(q.dangling) && q.dangling.length) out.push(chip("fail", `Verweis ${q.dangling.map(n => "[" + Number(n) + "]").join(", ")} ohne Quelle`));
    return `<div class="reader-quality" aria-label="Qualität des Dokuments">${out.join("")}</div>`;
  }
  function readerDocHtml(d) {
    if (!d) return `<div class="intel-empty">Kein Dokument ausgewählt.</div>`;
    const href = esc(intelHref(d));
    const head = `<div class="reader-docbar"><span class="intel-kind">${esc(d.label || INTEL_LABEL[d.kind] || d.kind)}</span><b>${esc(d.name)}</b>` +
      `<span class="intel-meta">${esc(d.where || "")}${d.where ? " · " : ""}${de(d.modified)}</span><a class="chip" href="${href}" target="_blank" rel="noopener">Öffnen ↗</a></div>`;
    if (d.mode === "md" && typeof d.html === "string") {
      const cut = d.truncated && d.html.indexOf("gekürzt") < 0 ? `<div class="intel-warn">… gekürzt: für den vollen Text die Datei öffnen.</div>` : "";
      return head + readerQualityHtml(d.quality) + `<div class="md">${d.html}</div>` + cut;
    }
    if (d.mode === "page" && typeof d.html === "string") return head + `<iframe class="reader-frame" sandbox="" title="${esc(d.name)}" srcdoc="${esc(d.html)}"></iframe>`;
    if (d.mode === "frame") return head + `<iframe class="reader-frame" sandbox="" title="${esc(d.name)}" src="${href}" loading="lazy"></iframe>`;
    return head + `<div class="intel-empty">Dieses Dokument wird nicht eingebettet. <a href="${href}" target="_blank" rel="noopener">Datei öffnen</a>.</div>`;
  }
  function readerSwitchHtml(docs, active) {
    if (!docs || !docs.length) return "";
    return `<div class="reader-switch" role="group" aria-label="Dokumente">` + docs.map((d, i) =>
      `<button type="button" class="chip${i === active ? " on" : ""}" data-doc="${i}" aria-pressed="${i === active}">${esc(d.label || INTEL_LABEL[d.kind] || d.kind)} <span class="reader-date">${de(d.modified)}</span></button>`).join("") + `</div>`;
  }

  return {
    TODAY, STAGES, OPEN, load, days, esc, de, pill, heat, heatClass, scoreBadge,
    folder, health, healthDot, prioBadge, sortable, store, donut, bars, css, PALETTE, chart,
    openDrawer, norm, renderSvgFunnel, intelHtml, intelCount, intelStamp, intelKey, cockpitLink, readerGroups, readerDocHtml, readerSwitchHtml, readerQualityHtml
  };
})();
