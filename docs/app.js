(function () {
  "use strict";

  var TYPE_LABELS = { publication: "Publication", preprint: "Preprint", clinical_trial: "Clinical trial" };
  var state = { findings: [] };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function safeUrl(url) {
    return /^https:\/\//i.test(url || "") ? url : "#";
  }

  function formatDate(iso) {
    if (!iso) return "never";
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString("en-US", {
      timeZone: "America/New_York", dateStyle: "medium", timeStyle: "short"
    }) + " ET";
  }

  function nextRefresh() {
    // Next Monday 7 p.m. in America/New_York.
    var now = new Date();
    var ny = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
    var target = new Date(ny);
    target.setHours(19, 0, 0, 0);
    var days = (1 - ny.getDay() + 7) % 7;
    if (days === 0 && ny >= target) days = 7;
    target.setDate(target.getDate() + days);
    return target.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" }) + ", 7:00 p.m. ET";
  }

  function renderHeader(data) {
    var meta = document.getElementById("meta");
    var text = "Last updated: " + formatDate(data.generated_at);
    if (data.period_start && data.period_end) text += " · Covering " + data.period_start + " to " + data.period_end;
    text += " · Next refresh: " + nextRefresh();
    if (data.ai_model) text += " · Summaries by " + data.ai_model;
    meta.textContent = text;
    document.getElementById("overview").textContent = data.overview || "";

    var stats = document.getElementById("stats");
    stats.textContent = "";
    var byType = (data.stats && data.stats.by_type) || {};
    stats.appendChild(statBox(data.findings.length, "Findings"));
    Object.keys(TYPE_LABELS).forEach(function (t) {
      stats.appendChild(statBox(byType[t] || 0, TYPE_LABELS[t] + "s"));
    });
    if (data.errors && data.errors.length) {
      stats.appendChild(el("p", "warning", "Some sources were unavailable this week: " + data.errors.join(", ")));
    }

    var select = document.getElementById("category-filter");
    Object.keys((data.stats && data.stats.by_category) || {}).forEach(function (c) {
      var opt = el("option", null, c + " (" + data.stats.by_category[c] + ")");
      opt.value = c;
      select.appendChild(opt);
    });
  }

  function statBox(value, label) {
    var box = el("div", "stat");
    box.appendChild(el("span", "stat-value", String(value)));
    box.appendChild(el("span", "stat-label", label));
    return box;
  }

  function renderFinding(f, rank) {
    var card = el("article", "card finding");
    var head = el("div", "finding-head");
    head.appendChild(el("span", "badge type-" + f.type, TYPE_LABELS[f.type] || f.type));
    if (f.ai_significance) head.appendChild(el("span", "badge significance", "Significance " + f.ai_significance + "/10"));
    (f.phases || []).forEach(function (p) { head.appendChild(el("span", "badge", p)); });
    if (f.status) head.appendChild(el("span", "badge", f.status));
    head.appendChild(el("span", "rank", "#" + rank));
    card.appendChild(head);

    var h3 = el("h3");
    var link = el("a", null, f.title);
    link.href = safeUrl(f.url);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    h3.appendChild(link);
    card.appendChild(h3);

    var details = [f.venue, f.date, (f.authors || []).slice(0, 3).join(", ") + ((f.authors || []).length > 3 ? " et al." : "")]
      .filter(Boolean).join(" · ");
    if (details) card.appendChild(el("p", "details", details));
    var summary = f.ai_summary || f.summary;
    if (summary) card.appendChild(el("p", "summary", summary));
    if (f.interventions && f.interventions.length) {
      card.appendChild(el("p", "details", "Interventions: " + f.interventions.join(", ")));
    }

    var tags = el("div", "tags");
    (f.categories || []).concat(f.cancer_types || []).forEach(function (t) { tags.appendChild(el("span", "tag", t)); });
    card.appendChild(tags);
    return card;
  }

  function haystack(f) {
    return [f.title, f.summary, f.ai_summary, f.venue].concat(f.categories || [], f.cancer_types || [],
      f.conditions || [], f.interventions || []).join(" ").toLowerCase();
  }

  function renderFindings() {
    var q = document.getElementById("search").value.trim().toLowerCase();
    var type = document.getElementById("type-filter").value;
    var cat = document.getElementById("category-filter").value;
    var container = document.getElementById("findings");
    container.textContent = "";
    var shown = 0;
    state.findings.forEach(function (f, i) {
      if (type && f.type !== type) return;
      if (cat && (f.categories || []).indexOf(cat) === -1) return;
      if (q && haystack(f).indexOf(q) === -1) return;
      container.appendChild(renderFinding(f, i + 1));
      shown++;
    });
    if (!shown) container.appendChild(el("p", "empty", "No findings to display."));
  }

  function init() {
    fetch("data/results.json", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        data.findings = data.findings || [];
        state.findings = data.findings;
        renderHeader(data);
        renderFindings();
      })
      .catch(function (err) {
        document.getElementById("meta").textContent = "Could not load results (" + err.message + ").";
      });
    ["search", "type-filter", "category-filter"].forEach(function (id) {
      document.getElementById(id).addEventListener("input", renderFindings);
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
