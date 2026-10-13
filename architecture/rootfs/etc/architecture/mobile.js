// Makes the Structurizr diagram page usable on a phone, which it is not
// built for: pinch zoom (it only knows buttons and wheel), and below 768 px a
// view picker in place of the thumbnail column that otherwise eats the width.
// One finger pans natively (the viewport scrolls); two fingers zoom around
// their midpoint through structurizr.diagram.zoomTo.
(function () {
  "use strict";
  var start = null;

  var style = document.createElement("style");
  style.textContent =
    "@media (max-width: 767px) {" +
    "#diagramNavigationPanel, #diagramControls .col-2 { display: none !important; }" +
    "#diagramNavigationPanel ~ .col-10, #diagramControls .col-10 { flex: 0 0 100% !important; max-width: 100% !important; width: 100% !important; }" +
    "#diagramControls .btn { padding: 0.3rem 0.45rem; }" +
    "#embeddedControls { margin-bottom: env(safe-area-inset-bottom); }" +
    "#ha-view { display: block !important; }" +
    "}" +
    "#ha-view { display: none; width: calc(100% - 24px); margin: 6px 12px; padding: 8px; font-size: 16px;" +
    " background: inherit; color: inherit; border: 1px solid #8a8a8a; border-radius: 6px; }";
  document.head.appendChild(style);

  function picker() {
    var tiles = document.querySelectorAll("#diagramNavigation .diagramThumbnail");
    var bar = document.getElementById("diagramControls");
    if (!tiles.length || !bar || document.getElementById("ha-view")) { return !!document.getElementById("ha-view"); }
    var field = document.createElement("select");
    field.id = "ha-view";
    field.setAttribute("aria-label", /^de\b/i.test(navigator.language || "") ? "Ansicht" : "View");
    tiles.forEach(function (k, i) {
      var o = document.createElement("option");
      o.value = String(i);
      o.textContent = k.innerText.split("#")[0].replace(/\s+/g, " ").trim();
      if (k.classList.contains("diagramThumbnailActive")) { o.selected = true; }
      field.appendChild(o);
    });
    field.addEventListener("change", function () { tiles[Number(field.value)].click(); });
    window.addEventListener("hashchange", function () {
      setTimeout(function () {
        tiles.forEach(function (k, i) { if (k.classList.contains("diagramThumbnailActive")) { field.value = String(i); } });
      }, 300);
    });
    bar.appendChild(field);
    return true;
  }

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

  function prepare() {
    var v = viewport();
    if (v && !v.dataset.gestures) {
      v.dataset.gestures = "1";
      v.style.touchAction = "pan-x pan-y";
      v.style.webkitOverflowScrolling = "touch";
      // The diagram measured its viewport before the narrow layout applied.
      window.dispatchEvent(new Event("resize"));
    }
  }

  document.addEventListener("touchstart", function (e) {
    prepare();
    var v = viewport();
    if (e.touches.length === 2 && v && v.contains(e.target) && diagram()) {
      start = { distance: distance(e.touches), scale: scale() };
    }
  }, { passive: true });

  document.addEventListener("touchmove", function (e) {
    var v = viewport(), d = diagram(), s = svg();
    if (!start || e.touches.length !== 2 || !v || !d || !s) { return; }
    e.preventDefault();
    var target = Math.min(3, Math.max(0.01, start.scale * distance(e.touches) / start.distance));
    var current = scale();
    if (Math.abs(target - current) < 0.005) { return; }
    var p = midpoint(e.touches);
    var r = s.getBoundingClientRect();
    var localX = (p.x - r.left) / current, localY = (p.y - r.top) / current;
    d.zoomTo(target);
    var r2 = s.getBoundingClientRect();
    v.scrollBy(r2.left + localX * target - p.x, r2.top + localY * target - p.y);
  }, { passive: false });

  document.addEventListener("touchend", function (e) {
    if (e.touches.length < 2) { start = null; }
  }, { passive: true });

  // The diagram builds its viewport after load; prepare it before the first pinch.
  var tries = 0;
  var timer = setInterval(function () {
    prepare();
    var done = picker() && viewport() && viewport().dataset.gestures;
    if (done || ++tries > 60) { clearInterval(timer); }
  }, 500);
})();
