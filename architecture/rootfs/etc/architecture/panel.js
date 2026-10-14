// Fits Structurizr into a Home Assistant panel.
//
// Theme: the ingress iframe is same-origin with the Home Assistant frontend,
// so the page reads the theme's CSS variables and dark mode from the parent
// document and follows every change. Structurizr's own light/dark switch is
// replaced by that. Opened outside Home Assistant, the system setting decides.
//
// Phone: Structurizr's diagram pane has overflow hidden and pans only with a
// mouse. Here one finger pans, two fingers zoom around their midpoint, a
// double tap zooms in up to 1:1 and back to fit, and below 768 px a view picker
// replaces the thumbnail column.
(function () {
  "use strict";

  // ---------------------------------------------------------------- theme

  var VARS = {
    bg: ["--primary-background-color"],
    card: ["--card-background-color", "--ha-card-background", "--primary-background-color"],
    text: ["--primary-text-color"],
    muted: ["--secondary-text-color"],
    primary: ["--primary-color"],
    divider: ["--divider-color"],
    font: ["--ha-font-family-body", "--paper-font-body1_-_font-family"]
  };

  function parentDocument() {
    try {
      if (window.parent !== window && window.parent.document && window.parent.document.documentElement) {
        return window.parent.document;
      }
    } catch (e) { /* cross-origin: no theme */ }
    return null;
  }

  function luminance(colour) {
    var probe = document.createElement("span");
    probe.style.color = colour;
    document.body.appendChild(probe);
    var m = getComputedStyle(probe).color.match(/\d+(\.\d+)?/g);
    probe.remove();
    if (!m) { return 1; }
    return (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
  }

  function readTheme() {
    var d = parentDocument();
    if (!d) { return null; }
    var cs = d.defaultView.getComputedStyle(d.documentElement);
    var theme = {};
    Object.keys(VARS).forEach(function (key) {
      theme[key] = "";
      VARS[key].some(function (name) { theme[key] = cs.getPropertyValue(name).trim(); return theme[key] !== ""; });
    });
    if (!theme.bg) { return null; }
    var ha = d.querySelector("home-assistant");
    var dark = ha && ha.hass && ha.hass.themes ? ha.hass.themes.darkMode : undefined;
    theme.dark = typeof dark === "boolean" ? dark : luminance(theme.bg) < 0.4;
    return theme;
  }

  var current = null;

  function systemDark() {
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  function isDark() {
    return current ? current.dark : systemDark();
  }

  function applyTheme() {
    var theme = readTheme();
    var root = document.documentElement;
    var signature = JSON.stringify(theme);
    if (signature === JSON.stringify(current) && root.dataset.haTheme) { return; }
    current = theme;
    root.dataset.haTheme = "1";
    if (theme) {
      root.classList.add("ha-themed");
      Object.keys(VARS).forEach(function (key) {
        if (theme[key]) { root.style.setProperty("--ha-" + key, theme[key]); }
      });
    } else {
      root.classList.remove("ha-themed");
    }
    var s = window.structurizr;
    if (s && s.ui && s.ui.changeRenderingMode) {
      s.ui.changeRenderingMode();
    }
    if (s && s.diagram && s.diagram.isDarkMode && s.diagram.isDarkMode() !== isDark()) {
      s.diagram.setDarkMode(isDark());
    }
  }

  if (window.structurizr && window.structurizr.ui) {
    // Home Assistant decides, not Structurizr's cookie.
    window.structurizr.ui.isDarkMode = isDark;
    window.structurizr.ui.getRenderingMode = function () { return "system"; };
  }

  var style = document.createElement("style");
  style.textContent = [
    // Structurizr's own light/dark/system links would fight the theme.
    "#renderingModeLightLink, #renderingModeDarkLink, #renderingModeSystemLink, p:has(> #renderingModeLightLink) { display: none !important; }",
    "html.ha-themed, html.ha-themed[data-bs-theme] {",
    "  --bs-body-bg: var(--ha-bg); --bs-body-color: var(--ha-text); --bs-emphasis-color: var(--ha-text);",
    "  --bs-secondary-color: var(--ha-muted); --bs-border-color: var(--ha-divider);",
    "  --bs-secondary-bg: var(--ha-card); --bs-tertiary-bg: var(--ha-card);",
    "  --bs-link-color: var(--ha-primary); --bs-link-hover-color: var(--ha-primary);",
    "  --bs-body-font-family: var(--ha-font, inherit); --bs-font-sans-serif: var(--ha-font, inherit);",
    "  color-scheme: light; accent-color: var(--ha-primary);",
    "}",
    "html.ha-themed[data-bs-theme=dark] { color-scheme: dark; }",
    "html.ha-themed body { background: var(--ha-bg) !important; color: var(--ha-text) !important; font-family: var(--ha-font, inherit); }",
    "html.ha-themed a, html.ha-themed a:hover { color: var(--ha-primary) !important; }",
    "html.ha-themed #diagramControls, html.ha-themed #diagramNavigationPanel, html.ha-themed #diagramNavigation { background: var(--ha-bg) !important; }",
    "html.ha-themed #diagram, html.ha-themed #diagram-viewport { background: var(--ha-bg) !important; }",
    "html.ha-themed #diagram-canvas, html.ha-themed .joint-paper-background { background-color: var(--ha-card) !important; }",
    "html.ha-themed .btn-default, html.ha-themed .btn, html.ha-themed .form-control, html.ha-themed select {",
    "  background-color: var(--ha-card) !important; color: var(--ha-text) !important; border-color: var(--ha-divider) !important; }",
    "html.ha-themed .diagramThumbnail img, html.ha-themed .thumbnail img { background-color: var(--ha-card); }",
    "html.ha-themed[data-bs-theme=dark] img.icon-btn, html.ha-themed[data-bs-theme=dark] img.icon-sm { filter: invert(1); }",
    "#ha-view { display: none; flex: 1 1 auto; min-width: 0; height: 40px; padding: 0 10px; font-size: 16px;",
    "  background: inherit; color: inherit; border: 1px solid var(--ha-divider, #8a8a8a); border-radius: 8px; }",
    "@media (max-width: 767px) {",
    "  #diagramNavigationPanel, #diagramControls .col-2, .workspaceLogo, #workspaceLogoAnchor { display: none !important; }",
    "  #diagramNavigationPanel ~ .col-10, #diagramControls .col-10 { flex: 0 0 100% !important; max-width: 100% !important; width: 100% !important; }",
    "  #diagramControls .form-group { display: flex !important; align-items: center; gap: 8px; padding: 8px 12px; margin: 0; }",
    "  #diagramControls .form-group > .btn-group:not(:first-child), #diagramControls .form-group ~ * { display: none !important; }",
    "  #diagramControls .btn { min-width: 40px; min-height: 40px; padding: 0.3rem 0.5rem; }",
    "  #ha-view { display: block; }",
    "  #embeddedControls { margin-bottom: env(safe-area-inset-bottom); }",
    // Summary, documentation, decisions: the side column moves above the content as a row of links.
    "  .row { margin-left: 0 !important; margin-right: 0 !important; }",
    "  .row > .col-2, .row > .col-10 { flex: 0 0 100% !important; max-width: 100% !important; width: 100% !important; }",
    "  .row > .col-2[style] { padding: 8px 12px !important; margin-bottom: 0 !important; }",
    "  #navigationPanel { display: flex !important; flex-wrap: wrap; gap: 4px 16px; }",
    "  #navigationPanel .navigationItem { margin: 0 !important; }",
    "  #navigationPanel a { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; }",
    "  .col-10.centered[style] { text-align: left !important; padding: 8px 12px !important; }",
    "  .topNavigationItem, #searchForm, #searchForm .form-inline, #searchForm .form-group { display: block !important; margin: 0 !important; width: 100% !important; }",
    "  input.form-control { max-width: 100% !important; width: 100% !important; box-sizing: border-box; }",
    "  img, svg, table, pre { max-width: 100%; }",
    "  pre, table { overflow-x: auto; display: block; }",
    "}"
  ].join("\n");
  document.head.appendChild(style);

  applyTheme();
  var parentDoc = parentDocument();
  if (parentDoc && window.MutationObserver) {
    new MutationObserver(applyTheme).observe(parentDoc.documentElement, { attributes: true, attributeFilter: ["style", "class"] });
  }
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  }
  // shortcut: the dark-mode flag can change without a style change on some HA versions; a slow poll covers that.
  setInterval(applyTheme, 5000);

  // ---------------------------------------------------------------- view picker

  function picker() {
    var tiles = document.querySelectorAll("#diagramNavigation .diagramThumbnail");
    var group = document.querySelector("#diagramControls .form-group");
    if (document.getElementById("ha-view")) { return true; }
    if (!tiles.length || !group) { return false; }
    var field = document.createElement("select");
    field.id = "ha-view";
    field.setAttribute("aria-label", /^de\b/i.test(navigator.language || "") ? "Ansicht" : "View");
    tiles.forEach(function (tile, i) {
      var o = document.createElement("option");
      o.value = String(i);
      o.textContent = tile.innerText.split("#")[0].replace(/\s+/g, " ").trim();
      if (tile.classList.contains("diagramThumbnailActive")) { o.selected = true; }
      field.appendChild(o);
    });
    field.addEventListener("change", function () { tiles[Number(field.value)].click(); });
    window.addEventListener("hashchange", function () {
      setTimeout(function () {
        tiles.forEach(function (tile, i) { if (tile.classList.contains("diagramThumbnailActive")) { field.value = String(i); } });
      }, 300);
    });
    var first = group.querySelector(".btn-group");
    group.insertBefore(field, first ? first.nextSibling : null);
    return true;
  }

  // ---------------------------------------------------------------- gestures

  function viewport() { return document.getElementById("diagram-viewport"); }
  function diagram() { return window.structurizr && window.structurizr.diagram; }
  function svg() { return document.querySelector("#diagram-canvas svg"); }
  function distance(t) { return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY); }
  function midpoint(t) { return { x: (t[0].clientX + t[1].clientX) / 2, y: (t[0].clientY + t[1].clientY) / 2 }; }

  function scale() {
    var g = document.querySelector("#diagram-canvas svg .joint-layers, #diagram-canvas svg .joint-viewport");
    var m = g && g.transform && g.transform.baseVal.consolidate();
    return m ? m.matrix.a : 1;
  }

  // Zooms to target and keeps the diagram point under (x, y) where it is.
  function zoomAround(target, x, y) {
    var v = viewport(), d = diagram(), s = svg();
    if (!v || !d || !s) { return; }
    var before = scale();
    var r = s.getBoundingClientRect();
    var localX = (x - r.left) / before, localY = (y - r.top) / before;
    d.zoomTo(target);
    var r2 = s.getBoundingClientRect();
    v.scrollBy(r2.left + localX * target - x, r2.top + localY * target - y);
  }

  function prepare() {
    var v = viewport();
    if (v && !v.dataset.gestures) {
      v.dataset.gestures = "1";
      v.style.touchAction = "none";
      // The diagram measured its viewport before the narrow layout applied.
      window.dispatchEvent(new Event("resize"));
    }
  }

  var pinch = null, pan = null, lastTap = 0;

  // Capture phase on window: runs before JointJS, which would otherwise take
  // the drag as moving an element.
  window.addEventListener("touchstart", function (e) {
    prepare();
    var v = viewport();
    if (!v || !v.contains(e.target) || !diagram()) { return; }
    if (e.touches.length === 2) {
      pan = null;
      pinch = { distance: distance(e.touches), scale: scale() };
    } else if (e.touches.length === 1) {
      pan = { x: e.touches[0].clientX, y: e.touches[0].clientY, moved: false };
    }
  }, { capture: true, passive: true });

  window.addEventListener("touchmove", function (e) {
    var v = viewport();
    if (!v) { return; }
    if (pinch && e.touches.length === 2) {
      e.preventDefault();
      e.stopImmediatePropagation();
      var target = Math.min(3, Math.max(0.01, pinch.scale * distance(e.touches) / pinch.distance));
      if (Math.abs(target - scale()) < 0.005) { return; }
      var p = midpoint(e.touches);
      zoomAround(target, p.x, p.y);
    } else if (pan && e.touches.length === 1) {
      var t = e.touches[0];
      var dx = t.clientX - pan.x, dy = t.clientY - pan.y;
      if (!pan.moved && Math.hypot(dx, dy) < 8) { return; }
      pan.moved = true;
      e.preventDefault();
      e.stopImmediatePropagation();
      v.scrollBy(-dx, -dy);
      pan.x = t.clientX;
      pan.y = t.clientY;
    }
  }, { capture: true, passive: false });

  window.addEventListener("touchend", function (e) {
    if (e.touches.length < 2) { pinch = null; }
    if (pan && e.touches.length === 0) {
      var tapped = !pan.moved, x = pan.x, y = pan.y;
      pan = null;
      if (!tapped) { e.stopImmediatePropagation(); return; }
      var now = Date.now();
      if (now - lastTap < 300) {
        lastTap = 0;
        var d = diagram();
        // Each double tap zooms in threefold up to 1:1; at 1:1 it returns to the whole diagram.
        if (d && scale() < 0.99) { zoomAround(Math.min(1, scale() * 3), x, y); }
        else if (d && d.zoomToWidthOrHeight) { d.zoomToWidthOrHeight(); }
      } else {
        lastTap = now;
      }
    }
  }, { capture: true, passive: true });

  // The diagram builds its viewport after load; prepare it before the first touch.
  var tries = 0;
  var timer = setInterval(function () {
    prepare();
    var done = picker() && viewport() && viewport().dataset.gestures;
    if (done || ++tries > 60) { clearInterval(timer); }
  }, 500);
})();
