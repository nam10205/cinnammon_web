(function () {
  var box = document.getElementById("order-progress");
  if (!box) return;
  var url = box.dataset.progressUrl;
  var timer = null;
  function render(d) {
    d.steps.forEach(function (s) {
      var li = box.querySelector('[data-step="' + s.name + '"]');
      if (!li) return;
      li.classList.toggle("list-group-item-success", s.done);
      li.querySelector("[data-at]").textContent = s.at || "";
    });
    document.getElementById("order-status").textContent = d.status;
    document.getElementById("order-payment").textContent = d.payment_status;
    var form = document.getElementById("cancel-form");
    if (form) form.hidden = !(d.status === "placed" || d.status === "processing");
    if (d.status === "delivered" || d.status === "cancelled") clearInterval(timer);
  }
  function poll() {
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) render(d); })
      .catch(function () {});
  }
  timer = setInterval(poll, 5000);
})();
