(function () {
  var btn = document.getElementById('mic');
  if (!btn) return;
  var form = btn.closest('form');
  var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec || !form) { btn.hidden = true; return; }
  btn.addEventListener('click', function () {
    var rec = new Rec();
    rec.lang = document.documentElement.lang === 'vi' ? 'vi-VN' : 'en-US';
    rec.interimResults = false;
    rec.onresult = function (e) {
      form.elements['q'].value = e.results[0][0].transcript;
      form.elements['mode'].value = 'voice';
      form.submit();
    };
    rec.start();
  });
})();
