// Ingress path shim for Prefect UI (Vue Router SPA)
//
// Problem: Through HA ingress the browser sits at /api/hassio_ingress/<token>/
// but Vue Router's base is "/" so it sees an unknown route and shows 404.
//
// Fix: Patch the History API to keep URLs within the ingress path, and
// after the Vue app mounts, programmatically navigate to the correct route.
(function () {
  var base = window.location.pathname;
  if (!base || base === '/') return; // not behind ingress
  if (!base.endsWith('/')) base += '/';

  // --- 1. Patch pushState / replaceState -----------------------------------
  // Vue Router calls history.pushState("/dashboard") – we rewrite to
  // "/api/hassio_ingress/<token>/dashboard" so the browser stays in ingress.
  var origPush = history.pushState;
  var origReplace = history.replaceState;

  function fixUrl(u) {
    if (!u || typeof u !== 'string') return u;
    if (u.startsWith('/') && !u.startsWith(base)) return base + u.substring(1);
    return u;
  }

  history.pushState = function (s, t, u) {
    return origPush.call(this, s, t, fixUrl(u));
  };
  history.replaceState = function (s, t, u) {
    return origReplace.call(this, s, t, fixUrl(u));
  };

  // --- 2. Intercept popstate (back / forward) ------------------------------
  // Without this, Vue Router reads window.location.pathname on popstate,
  // sees the full ingress path, and shows 404.  We stop the event before
  // Vue Router can process it and manually navigate to the correct route.
  window.addEventListener(
    'popstate',
    function (e) {
      e.stopImmediatePropagation();
      var router = getRouter();
      if (router) router.replace(getRoute()).catch(function () {});
    },
    true // capture phase – runs before Vue Router's listener
  );

  // --- 3. Fix initial route after Vue app mounts ---------------------------
  var attempts = 0;
  var timer = setInterval(function () {
    var router = getRouter();
    if (router) {
      clearInterval(timer);
      router.replace(getRoute()).catch(function () {});
    } else if (++attempts > 200) {
      // 200 × 50 ms = 10 s – give up
      clearInterval(timer);
    }
  }, 50);

  // --- helpers -------------------------------------------------------------
  function getRoute() {
    var p = window.location.pathname;
    if (p.startsWith(base)) return '/' + p.substring(base.length);
    return '/';
  }

  function getRouter() {
    var el =
      document.querySelector('[data-v-app]') ||
      document.getElementById('app');
    return (
      el &&
      el.__vue_app__ &&
      el.__vue_app__.config.globalProperties.$router
    );
  }
})();
