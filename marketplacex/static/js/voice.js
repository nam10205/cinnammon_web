(function () {
  var btn = document.getElementById('mic');
  if (!btn) return;
  var form = btn.closest('form');
  var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec || !form) { btn.hidden = true; return; }
  var input = form.elements['q'], mode = form.elements['mode'];
  var icon = btn.querySelector('i');

  // A live caption under the search box: what the mic hears, word by word.
  var panel = document.createElement('div');
  panel.className = 'voice-panel';
  panel.hidden = true;
  panel.setAttribute('role', 'status');
  panel.innerHTML = '<span class="voice-wave" aria-hidden="true"><i></i><i></i><i></i><i></i></span>' +
    '<span class="voice-body"><span class="voice-state"></span><span class="voice-words"></span></span>';
  form.appendChild(panel);
  var state = panel.querySelector('.voice-state'), words = panel.querySelector('.voice-words');

  var rec = null, kept = '', failed = false;

  function show(title, text, cls) {
    panel.hidden = false;
    panel.className = 'voice-panel' + (cls ? ' ' + cls : '');
    state.textContent = title;
    words.textContent = text;
  }

  function stop() { if (rec) rec.stop(); }

  function start() {
    rec = new Rec();
    rec.lang = 'vi-VN'; // shoppers speak Vietnamese; English brand names still come through
    rec.continuous = true;
    rec.interimResults = true;
    kept = ''; failed = false;

    rec.onstart = function () {
      btn.classList.add('listening');
      btn.setAttribute('aria-pressed', 'true');
      btn.setAttribute('aria-label', 'Stop voice search');
      icon.className = 'bi bi-stop-fill';
      show('Listening… tap the mic again to stop', 'Hãy nói tên sản phẩm hoặc thương hiệu', 'is-live is-empty');
    };
    rec.onresult = function (e) {
      var heard = '';
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) kept += e.results[i][0].transcript;
        else heard += e.results[i][0].transcript;
      }
      var text = (kept + heard).trim();
      input.value = text;
      mode.value = 'voice';
      show('Listening… tap the mic again to stop', text || 'Hãy nói tên sản phẩm hoặc thương hiệu', 'is-live' + (text ? '' : ' is-empty'));
    };
    rec.onerror = function (e) {
      failed = true;
      var why = {
        'not-allowed': 'Microphone access is blocked. Allow it in the address bar and try again.',
        'service-not-allowed': 'Microphone access is blocked. Allow it in the address bar and try again.',
        'no-speech': 'No speech heard. Tap the mic and try again.',
        'audio-capture': 'No microphone found.',
        'network': 'Voice search needs an internet connection.'
      }[e.error];
      if (e.error !== 'aborted') show('Voice search stopped', why || 'Something went wrong. Tap the mic to try again.', 'is-error');
    };
    rec.onend = function () {
      rec = null;
      btn.classList.remove('listening');
      btn.setAttribute('aria-pressed', 'false');
      btn.setAttribute('aria-label', 'Voice search');
      icon.className = 'bi bi-mic';
      if (failed) return;
      if (input.value.trim()) {
        show('Got it. Press search when ready', input.value.trim(), 'is-done');
        input.focus();
      } else {
        panel.hidden = true;
      }
    };
    try { rec.start(); } catch (err) { rec = null; }
  }

  btn.setAttribute('aria-pressed', 'false');
  btn.addEventListener('click', function () { rec ? stop() : start(); });
  input.addEventListener('input', function () { mode.value = 'text'; if (!rec) panel.hidden = true; });
  form.addEventListener('submit', function () { stop(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && rec) stop(); });
})();
