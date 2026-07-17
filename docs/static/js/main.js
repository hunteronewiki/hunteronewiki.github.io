/* Kingshot Wiki — client-side behavior. No frameworks, no build step. */

(function () {
  "use strict";

  var ROOT = window.SITE_ROOT || "./";
  var indexPromise = null;

  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetch(ROOT + "search-index.json")
        .then(function (r) { return r.json(); })
        .catch(function () { return []; });
    }
    return indexPromise;
  }

  function scoreEntry(entry, qLower) {
    var title = entry.title.toLowerCase();
    if (title === qLower) return 100;
    if (title.startsWith(qLower)) return 80;
    if (title.includes(qLower)) return 60;
    for (var i = 0; i < entry.tags.length; i++) {
      if (entry.tags[i].toLowerCase().includes(qLower)) return 40;
    }
    if (entry.categoryLabel.toLowerCase().includes(qLower)) return 20;
    return 0;
  }

  function search(list, query) {
    var q = query.trim().toLowerCase();
    if (!q) return [];
    return list
      .map(function (e) { return { entry: e, score: scoreEntry(e, q) }; })
      .filter(function (r) { return r.score > 0; })
      .sort(function (a, b) { return b.score - a.score; })
      .map(function (r) { return r.entry; });
  }

  function urlFor(entry) {
    return ROOT + entry.url.replace(/^\//, "");
  }

  /* ---------------------------------------------------------- header search */

  function initHeaderSearch() {
    var input = document.getElementById("searchInput");
    var results = document.getElementById("searchResults");
    if (!input || !results) return;
    var activeIndex = -1;
    var currentMatches = [];

    function render(matches) {
      currentMatches = matches.slice(0, 8);
      activeIndex = -1;
      if (currentMatches.length === 0) {
        results.innerHTML = '<div class="sr-empty">No matches</div>';
        results.hidden = false;
        return;
      }
      results.innerHTML = currentMatches
        .map(function (e) {
          return (
            '<a href="' + urlFor(e) + '">' +
            '<span class="sr-title">' + escapeHtml(e.title) + "</span>" +
            '<span class="sr-cat">' + escapeHtml(e.categoryLabel) + "</span>" +
            "</a>"
          );
        })
        .join("");
      results.hidden = false;
    }

    function escapeHtml(s) {
      var d = document.createElement("div");
      d.textContent = s;
      return d.innerHTML;
    }

    input.addEventListener("input", function () {
      var q = input.value;
      if (!q.trim()) {
        results.hidden = true;
        return;
      }
      loadIndex().then(function (list) { render(search(list, q)); });
    });

    input.addEventListener("keydown", function (e) {
      var links = results.querySelectorAll("a");
      if (e.key === "ArrowDown" && links.length) {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, links.length - 1);
        links.forEach(function (l, i) { l.classList.toggle("active", i === activeIndex); });
      } else if (e.key === "ArrowUp" && links.length) {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        links.forEach(function (l, i) { l.classList.toggle("active", i === activeIndex); });
      } else if (e.key === "Enter") {
        if (activeIndex >= 0 && links[activeIndex]) {
          window.location.href = links[activeIndex].getAttribute("href");
        } else if (input.value.trim()) {
          window.location.href = ROOT + "search/?q=" + encodeURIComponent(input.value.trim());
        }
      } else if (e.key === "Escape") {
        results.hidden = true;
        input.blur();
      }
    });

    document.addEventListener("click", function (e) {
      if (!results.contains(e.target) && e.target !== input) {
        results.hidden = true;
      }
    });
  }

  /* ---------------------------------------------------------- search page */

  function initSearchPage() {
    var pageInput = document.getElementById("searchPageInput");
    var pageResults = document.getElementById("searchPageResults");
    var hint = document.getElementById("searchPageHint");
    if (!pageInput || !pageResults) return;

    var params = new URLSearchParams(window.location.search);
    var initialQ = params.get("q") || "";
    pageInput.value = initialQ;

    function renderResults(matches, query) {
      if (!query.trim()) {
        pageResults.innerHTML = "";
        if (hint) hint.textContent = "Type below, or use the search box at the top of any page.";
        return;
      }
      if (hint) hint.textContent = matches.length + ' result' + (matches.length === 1 ? "" : "s") + ' for "' + query + '"';
      pageResults.innerHTML = matches
        .map(function (e) {
          return '<li><a href="' + urlFor(e) + '">' + e.title + " <small style=\"color:var(--text-faint)\">(" + e.categoryLabel + ")</small></a></li>";
        })
        .join("");
    }

    loadIndex().then(function (list) {
      renderResults(search(list, initialQ), initialQ);
      pageInput.addEventListener("input", function () {
        var q = pageInput.value;
        renderResults(search(list, q), q);
        var url = new URL(window.location.href);
        if (q) { url.searchParams.set("q", q); } else { url.searchParams.delete("q"); }
        window.history.replaceState({}, "", url);
      });
    });
  }

  /* ---------------------------------------------------------- sidebar (mobile) */

  function initSidebar() {
    var toggle = document.getElementById("sidebarToggle");
    var sidebar = document.getElementById("sidebar");
    var backdrop = document.getElementById("sidebarBackdrop");
    if (!toggle || !sidebar || !backdrop) return;

    function close() {
      sidebar.classList.remove("open");
      backdrop.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }
    function open() {
      sidebar.classList.add("open");
      backdrop.classList.add("open");
      toggle.setAttribute("aria-expanded", "true");
    }
    toggle.addEventListener("click", function () {
      sidebar.classList.contains("open") ? close() : open();
    });
    backdrop.addEventListener("click", close);
    sidebar.addEventListener("click", function (e) {
      if (e.target.tagName === "A") close();
    });
  }

  /* ---------------------------------------------------------- random page */

  function initRandomPage() {
    var btn = document.getElementById("randomPageBtn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      loadIndex().then(function (list) {
        if (!list.length) return;
        var pick = list[Math.floor(Math.random() * list.length)];
        window.location.href = urlFor(pick);
      });
    });
  }

  /* ---------------------------------------------------------- copy code */

  window.copyCode = function (btn) {
    var pre = btn.parentElement.querySelector("code");
    if (!pre) return;
    var text = pre.textContent;
    var done = function () {
      var original = btn.textContent;
      btn.textContent = "Copied!";
      btn.classList.add("copied");
      setTimeout(function () {
        btn.textContent = original;
        btn.classList.remove("copied");
      }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(done);
    } else {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta);
      done();
    }
  };

  /* ---------------------------------------------------------- milestone calendar */

  var MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];

  function pad2(n) { return n < 10 ? "0" + n : "" + n; }

  function escapeHtmlText(s) {
    var d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function initMilestoneCalendars() {
    var calendars = document.querySelectorAll(".milestone-calendar");
    calendars.forEach(function (cal) {
      var dataEl = cal.querySelector(".mc-data");
      var entries = [];
      try { entries = JSON.parse(dataEl.textContent); } catch (e) { entries = []; }

      var byDate = {};
      entries.forEach(function (e) {
        if (e.date) { (byDate[e.date] = byDate[e.date] || []).push(e); }
      });

      var today = new Date();
      var todayKey = today.getUTCFullYear() + "-" + pad2(today.getUTCMonth() + 1) + "-" + pad2(today.getUTCDate());
      var view = { year: today.getUTCFullYear(), month: today.getUTCMonth() };

      var monthLabel = cal.querySelector(".mc-month-label");
      var grid = cal.querySelector(".mc-grid");
      var detail = cal.querySelector(".mc-detail");

      function showDetail(e) {
        detail.hidden = false;
        detail.innerHTML =
          '<button type="button" class="mc-detail-close" aria-label="Close">&times;</button>' +
          '<div class="mc-detail-title">' + escapeHtmlText(e.title) + "</div>" +
          '<div class="mc-detail-meta">' + escapeHtmlText(e.category || "General") +
          (e.date ? " &middot; " + escapeHtmlText(e.date) + (e.time ? " " + escapeHtmlText(e.time) + " UTC" : "") : "") +
          "</div>" +
          (e.notes ? '<div class="mc-detail-notes">' + e.notes + "</div>" : "");
        detail.querySelector(".mc-detail-close").addEventListener("click", function () {
          detail.hidden = true;
        });
      }

      function render() {
        monthLabel.textContent = MONTH_NAMES[view.month] + " " + view.year;
        grid.innerHTML = "";
        detail.hidden = true;

        var startWeekday = new Date(Date.UTC(view.year, view.month, 1)).getUTCDay();
        var daysInMonth = new Date(Date.UTC(view.year, view.month + 1, 0)).getUTCDate();
        var totalCells = Math.ceil((startWeekday + daysInMonth) / 7) * 7;

        for (var i = 0; i < totalCells; i++) {
          var dayNum = i - startWeekday + 1;
          var cellDiv = document.createElement("div");
          if (dayNum < 1 || dayNum > daysInMonth) {
            cellDiv.className = "mc-cell mc-cell-empty";
            grid.appendChild(cellDiv);
            continue;
          }
          var dateKey = view.year + "-" + pad2(view.month + 1) + "-" + pad2(dayNum);
          cellDiv.className = "mc-cell" + (dateKey === todayKey ? " mc-cell-today" : "");

          var dayLabel = document.createElement("div");
          dayLabel.className = "mc-day-num";
          dayLabel.textContent = dayNum;
          cellDiv.appendChild(dayLabel);

          (byDate[dateKey] || []).forEach(function (e) {
            var marker = document.createElement("button");
            marker.type = "button";
            marker.className = "mc-marker";
            marker.textContent = e.title;
            marker.addEventListener("click", function () { showDetail(e); });
            cellDiv.appendChild(marker);
          });
          grid.appendChild(cellDiv);
        }
      }

      cal.querySelector(".mc-prev").addEventListener("click", function () {
        view.month--; if (view.month < 0) { view.month = 11; view.year--; }
        render();
      });
      cal.querySelector(".mc-next").addEventListener("click", function () {
        view.month++; if (view.month > 11) { view.month = 0; view.year++; }
        render();
      });
      cal.querySelector(".mc-today-btn").addEventListener("click", function () {
        view.year = today.getUTCFullYear(); view.month = today.getUTCMonth();
        render();
      });

      render();
    });
  }

  /* ---------------------------------------------------------- hero stat widget */

  function initHeroStatWidgets() {
    document.querySelectorAll(".hero-stat-widget").forEach(function (widget) {
      var dataEl = widget.querySelector(".hsw-data");
      var payload;
      try { payload = JSON.parse(dataEl.textContent); } catch (e) { return; }
      var base = payload.base, mult = payload.multipliers;
      var slider = widget.querySelector(".hsw-slider");
      var starLabel = widget.querySelector(".hsw-star-value");
      var statEls = widget.querySelectorAll(".hsw-stat-value");

      function render() {
        var star = slider.value;
        var m = mult[star];
        starLabel.textContent = star + "\u2605";
        statEls.forEach(function (el) {
          var stat = el.getAttribute("data-stat");
          var val = Math.round(base[stat] * m);
          el.textContent = val.toLocaleString();
        });
      }
      slider.addEventListener("input", render);
      render();
    });
  }

  /* ---------------------------------------------------------- gear widget */

  function initGearWidgets() {
    var TROOP_ICONS = { Infantry: "\u{1F6E1}\uFE0F", Cavalry: "\u{1F40E}", Archer: "\u{1F3F9}" };
    document.querySelectorAll(".gear-widget").forEach(function (widget) {
      var dataEl = widget.querySelector(".gw-data");
      var pieces;
      try { pieces = JSON.parse(dataEl.textContent); } catch (e) { return; }
      var select = widget.querySelector(".gw-piece-select");
      var slider = widget.querySelector(".gw-slider");
      var levelLabel = widget.querySelector(".gw-level-value");
      var outLabel = widget.querySelector(".gw-output-label");
      var outValue = widget.querySelector(".gw-output-value");
      var troopBadge = widget.querySelector(".gw-troop-badge");

      function render() {
        var piece = pieces[select.value];
        var level = parseInt(slider.value, 10);
        levelLabel.textContent = level;
        var pct = piece.start + (piece.end - piece.start) * (level / 100);
        outLabel.textContent = piece.name + " \u2014 " + piece.stat;
        outValue.textContent = "+" + pct.toFixed(1) + "%";
        if (troopBadge) {
          troopBadge.className = "gw-troop-badge troop-badge troop-badge-" + (piece.troopClass || "");
          troopBadge.innerHTML = (TROOP_ICONS[piece.troop] || "") + " " + piece.troop;
        }
      }
      select.addEventListener("change", render);
      slider.addEventListener("input", render);
      render();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initHeaderSearch();
    initSearchPage();
    initSidebar();
    initRandomPage();
    initMilestoneCalendars();
    initHeroStatWidgets();
    initGearWidgets();
  });
})();
