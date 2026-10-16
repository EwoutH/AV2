// Highlight the downloads that match this computer.
(function () {
  var ua = navigator.userAgent, os = null;
  if (/Windows/.test(ua)) os = "windows-x64";
  else if (/Mac OS X/.test(ua)) os = "macos-arm64";
  else if (/Linux/.test(ua) && !/Android/.test(ua))
    os = /aarch64|arm64/.test(ua) ? "linux-arm64" : "linux-x64";
  if (os) document.querySelectorAll('[data-os="' + os + '"]').forEach(function (el) {
    el.classList.add("mine");
  });
})();

// Samples page: filter streams by text and feature. The URL hash selects a
// feature, so the landing page can link to e.g. samples/#hdr10.
(function () {
  var q = document.getElementById("q");
  if (!q) return;
  var buttons = document.querySelectorAll("[data-filter]");
  var active = null;

  function apply() {
    var words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    document.querySelectorAll("section.set").forEach(function (set) {
      var shown = 0;
      set.querySelectorAll("tbody tr").forEach(function (tr) {
        var text = tr.dataset.search, tags = tr.dataset.tags.split(" ");
        var ok = (!active || tags.indexOf(active) >= 0) &&
          words.every(function (w) { return text.indexOf(w) >= 0; });
        tr.hidden = !ok;
        if (ok) shown++;
      });
      set.querySelector(".table-wrap").hidden = shown === 0;
      set.querySelector(".empty").hidden = shown !== 0;
    });
    buttons.forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.filter === active ? "true" : "false");
    });
  }

  function fromHash() {
    var h = location.hash.slice(1);
    var known = Array.prototype.some.call(buttons, function (b) { return b.dataset.filter === h; });
    active = known ? h : null;
    apply();
  }

  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      active = active === b.dataset.filter ? null : b.dataset.filter;
      history.replaceState(null, "", active ? "#" + active : location.pathname);
      apply();
    });
  });
  q.addEventListener("input", apply);
  window.addEventListener("hashchange", fromHash);
  fromHash();
})();
