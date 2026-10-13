// Makes the Structurizr diagram page usable on a phone, which it is not
// built for: pinch zoom (it only knows buttons and wheel), and below 768 px a
// view picker in place of the thumbnail column that otherwise eats the width.
// One finger pans natively (the viewport scrolls); two fingers zoom around
// their midpoint through structurizr.diagram.zoomTo.
(function () {
  "use strict";
  var start = null;

  var stil = document.createElement("style");
  stil.textContent =
    "@media (max-width: 767px) {" +
    "#diagramNavigationPanel, #diagramControls .col-2 { display: none !important; }" +
    "#diagramNavigationPanel ~ .col-10, #diagramControls .col-10 { flex: 0 0 100% !important; max-width: 100% !important; width: 100% !important; }" +
    "#diagramControls .btn { padding: 0.3rem 0.45rem; }" +
    "#embeddedControls { margin-bottom: env(safe-area-inset-bottom); }" +
    "#ha-sicht { display: block !important; }" +
    "}" +
    "#ha-sicht { display: none; width: calc(100% - 24px); margin: 6px 12px; padding: 8px; font-size: 16px;" +
    " background: inherit; color: inherit; border: 1px solid #8a8a8a; border-radius: 6px; }";
  document.head.appendChild(stil);

  function auswahl() {
    var kacheln = document.querySelectorAll("#diagramNavigation .diagramThumbnail");
    var leiste = document.getElementById("diagramControls");
    if (!kacheln.length || !leiste || document.getElementById("ha-sicht")) { return !!document.getElementById("ha-sicht"); }
    var feld = document.createElement("select");
    feld.id = "ha-sicht";
    feld.setAttribute("aria-label", "Ansicht");
    kacheln.forEach(function (k, i) {
      var o = document.createElement("option");
      o.value = String(i);
      o.textContent = k.innerText.split("#")[0].replace(/\s+/g, " ").trim();
      if (k.classList.contains("diagramThumbnailActive")) { o.selected = true; }
      feld.appendChild(o);
    });
    feld.addEventListener("change", function () { kacheln[Number(feld.value)].click(); });
    window.addEventListener("hashchange", function () {
      setTimeout(function () {
        kacheln.forEach(function (k, i) { if (k.classList.contains("diagramThumbnailActive")) { feld.value = String(i); } });
      }, 300);
    });
    leiste.appendChild(feld);
    return true;
  }

  function viewport() { return document.getElementById("diagram-viewport"); }
  function diagram() { return window.structurizr && window.structurizr.diagram; }
  function svg() { return document.querySelector("#diagram-canvas svg"); }
  function abstand(t) { return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY); }
  function mitte(t) { return { x: (t[0].clientX + t[1].clientX) / 2, y: (t[0].clientY + t[1].clientY) / 2 }; }

  function massstab() {
    var g = document.querySelector("#diagram-canvas svg .joint-layers, #diagram-canvas svg .joint-viewport");
    var m = g && g.transform && g.transform.baseVal.consolidate();
    return m ? m.matrix.a : 1;
  }

  function vorbereiten() {
    var v = viewport();
    if (v && !v.dataset.gesten) {
      v.dataset.gesten = "1";
      v.style.touchAction = "pan-x pan-y";
      v.style.webkitOverflowScrolling = "touch";
      // The diagram measured its viewport before the narrow layout applied.
      window.dispatchEvent(new Event("resize"));
    }
  }

  document.addEventListener("touchstart", function (e) {
    vorbereiten();
    var v = viewport();
    if (e.touches.length === 2 && v && v.contains(e.target) && diagram()) {
      start = { abstand: abstand(e.touches), massstab: massstab() };
    }
  }, { passive: true });

  document.addEventListener("touchmove", function (e) {
    var v = viewport(), d = diagram(), s = svg();
    if (!start || e.touches.length !== 2 || !v || !d || !s) { return; }
    e.preventDefault();
    var ziel = Math.min(3, Math.max(0.01, start.massstab * abstand(e.touches) / start.abstand));
    var alt = massstab();
    if (Math.abs(ziel - alt) < 0.005) { return; }
    var p = mitte(e.touches);
    var r = s.getBoundingClientRect();
    var lokalX = (p.x - r.left) / alt, lokalY = (p.y - r.top) / alt;
    d.zoomTo(ziel);
    var r2 = s.getBoundingClientRect();
    v.scrollBy(r2.left + lokalX * ziel - p.x, r2.top + lokalY * ziel - p.y);
  }, { passive: false });

  document.addEventListener("touchend", function (e) {
    if (e.touches.length < 2) { start = null; }
  }, { passive: true });

  // The diagram builds its viewport after load; prepare it before the first pinch.
  var versuche = 0;
  var takt = setInterval(function () {
    vorbereiten();
    var fertig = auswahl() && viewport() && viewport().dataset.gesten;
    if (fertig || ++versuche > 60) { clearInterval(takt); }
  }, 500);
})();
