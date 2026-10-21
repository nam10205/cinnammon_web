(function () {
  var track = document.getElementById("hero-track");
  if (!track) return;
  var hero = track.closest(".hero");
  var slides = track.children;
  var dots = hero.querySelectorAll(".hero-dots button");
  var index = 0, timer = null;
  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function go(i) {
    index = (i + slides.length) % slides.length;
    track.scrollTo({ left: slides[index].offsetLeft, behavior: still ? "auto" : "smooth" });
    mark();
  }
  function mark() {
    dots.forEach(function (d, n) { d.setAttribute("aria-selected", n === index ? "true" : "false"); });
    hero.style.setProperty("--slide-ms", still ? "0ms" : "6500ms");
    hero.classList.remove("ticking"); void hero.offsetWidth; hero.classList.add("ticking");
  }
  function play() { if (!still && slides.length > 1) { stop(); timer = setInterval(function () { go(index + 1); }, 6500); mark(); } }
  function stop() { clearInterval(timer); timer = null; hero.classList.remove("ticking"); }

  dots.forEach(function (d, n) { d.addEventListener("click", function () { go(n); play(); }); });
  hero.querySelectorAll(".hero-arrow").forEach(function (b) {
    b.addEventListener("click", function () { go(index + Number(b.dataset.dir)); play(); });
  });
  track.addEventListener("scroll", function () {
    var n = Math.round(track.scrollLeft / track.clientWidth);
    if (n !== index && n < slides.length) { index = n; mark(); }
  }, { passive: true });
  hero.addEventListener("mouseenter", stop);
  hero.addEventListener("mouseleave", play);
  hero.addEventListener("focusin", stop);
  hero.addEventListener("focusout", play);
  document.addEventListener("visibilitychange", function () { document.hidden ? stop() : play(); });
  play();
})();
