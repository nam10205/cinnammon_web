(function () {
  var box = document.getElementById("order-progress");
  if (!box) return;
  var url = box.dataset.progressUrl;
  var timer = null;
  function stamp(el, value) {
    el.innerHTML = '<span class="st st-' + value + '">' + value + "</span>";
  }
  function render(d) {
    var final = d.status === "delivered" || d.status === "cancelled";
    var current = null;
    d.steps.forEach(function (s) { if (s.done) current = s.name; });
    box.querySelector(".punch").classList.toggle("is-cancelled", d.status === "cancelled");
    d.steps.forEach(function (s) {
      var li = box.querySelector('[data-step="' + s.name + '"]');
      if (!li) return;
      if (s.done && !li.classList.contains("is-done")) {
        li.classList.add("just-punched");
        setTimeout(function () { li.classList.remove("just-punched"); }, 700);
      }
      li.classList.toggle("is-done", s.done);
      li.classList.toggle("is-current", s.name === current && !final);
      li.querySelector("[data-at]").textContent = s.at ? s.at.slice(11, 19) : "";
    });
    stamp(document.getElementById("order-status"), d.status);
    stamp(document.getElementById("order-payment"), d.payment_status);
    var form = document.getElementById("cancel-form");
    if (form) form.hidden = !(d.status === "placed" || d.status === "processing");
    var hint = box.querySelector(".hint");
    if (hint && final) hint.hidden = true;
    if (final) clearInterval(timer);
    document.dispatchEvent(new CustomEvent("order:progress", { detail: d }));
  }
  function poll() {
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) render(d); })
      .catch(function () {});
  }
  timer = setInterval(poll, 5000);
})();
