(function () {
  var btn = document.getElementById('mic');
  if (!btn) return;
  var status = document.getElementById('voice-status');
  var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec) { status.textContent = 'Speech recognition is not supported in this browser — type the transcript instead.'; btn.disabled = true; return; }
  btn.addEventListener('click', function () {
    var rec = new Rec();
    rec.lang = 'en-US';
    rec.interimResults = false;
    status.textContent = 'Listening…';
    rec.onresult = function (e) {
      document.getElementById('transcript').value = e.results[0][0].transcript;
      status.textContent = 'Heard: ' + e.results[0][0].transcript;
      document.getElementById('voice-form').submit();
    };
    rec.onerror = function (e) { status.textContent = 'Voice input failed (' + e.error + ') — type the transcript instead.'; };
    rec.start();
  });
})();
