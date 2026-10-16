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

// Samples page: filter streams by text, feature, resolution and value
// ranges. The URL hash selects a feature, so the landing page can link to
// e.g. samples/#hdr10.
(function () {
  var q = document.getElementById("q");
  if (!q) return;
  var buttons = document.querySelectorAll("[data-filter]");
  var boxes = document.querySelectorAll("input[data-res]");
  var count = document.getElementById("count");
  var active = null;

  function fmt(v, unit) {
    if (unit === "bytes")
      return v >= 1e6 ? (v / 1e6).toFixed(1) + " MB" : Math.round(v / 1e3) + " kB";
    return v + (unit ? " " + unit : "");
  }

  // Two-handle sliders that step through the values present in the tables.
  var ranges = Array.prototype.map.call(document.querySelectorAll(".range"), function (el) {
    var values = JSON.parse(el.dataset.values), inputs = el.querySelectorAll("input");
    var r = { key: el.dataset.key, lo: values[0], hi: values[values.length - 1] };
    r.update = function (moved) {
      var a = +inputs[0].value, b = +inputs[1].value;
      if (a > b) { if (moved === inputs[0]) inputs[0].value = a = b; else inputs[1].value = b = a; }
      r.lo = values[a]; r.hi = values[b];
      var n = values.length - 1;
      el.querySelector(".range-fill").style.cssText = "left:" + (a / n * 100) + "%;right:" + (100 - b / n * 100) + "%";
      el.querySelector("output").textContent = r.lo === r.hi ? fmt(r.lo, el.dataset.unit)
        : fmt(r.lo, el.dataset.unit) + " – " + fmt(r.hi, el.dataset.unit);
      el.classList.toggle("set", a > 0 || b < n);
    };
    r.reset = function () { inputs[0].value = 0; inputs[1].value = values.length - 1; r.update(); };
    inputs.forEach(function (i) { i.addEventListener("input", function () { r.update(i); apply(); }); });
    r.update();
    return r;
  });

  function apply() {
    var words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    var res = {}, total = 0, shownAll = 0;
    boxes.forEach(function (b) { res[b.dataset.res] = b.checked; });
    document.querySelectorAll("section.set").forEach(function (set) {
      var shown = 0;
      set.querySelectorAll("tbody tr").forEach(function (tr) {
        var d = tr.dataset, tags = d.tags.split(" ");
        var ok = (!active || tags.indexOf(active) >= 0) &&
          (!d.res || res[d.res] !== false) &&
          ranges.every(function (r) {
            var v = d[r.key];
            return v === undefined || (+v >= r.lo && +v <= r.hi);
          }) &&
          words.every(function (w) { return d.search.indexOf(w) >= 0; });
        tr.hidden = !ok;
        total++;
        if (ok) shown++;
      });
      shownAll += shown;
      set.querySelector(".table-wrap").hidden = shown === 0;
      set.querySelector(".empty").hidden = shown !== 0;
    });
    count.textContent = shownAll === total ? total + " streams" : shownAll + " of " + total + " streams";
    buttons.forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.filter === active ? "true" : "false");
    });
  }

  boxes.forEach(function (b) { b.addEventListener("change", apply); });
  document.getElementById("reset").addEventListener("click", function () {
    q.value = "";
    active = null;
    boxes.forEach(function (b) { b.checked = true; });
    ranges.forEach(function (r) { r.reset(); });
    history.replaceState(null, "", location.pathname);
    apply();
  });

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
