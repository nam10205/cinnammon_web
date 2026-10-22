// VoiceSearchView from the voice search diagram. Steps 7-8 (searchByVoice, recognize speech) run in the
// browser's own speech service, set to Vietnamese; the server gets the confirmed text at step 14.
(function () {
  var btn = document.getElementById('mic');
  if (!btn) return;
  var form = btn.closest('form');
  var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec || !form) { btn.hidden = true; return; }
  var input = form.elements['q'], mode = form.elements['mode'];
  var icon = btn.querySelector('i');
  var HINT = 'Hãy nói tên sản phẩm hoặc thương hiệu';
  var BLOCKED = 'Microphone access is blocked. Allow it in the address bar and try again.';

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

  function setMic(listening) {
    btn.classList.toggle('listening', listening);
    btn.setAttribute('aria-pressed', listening ? 'true' : 'false');
    btn.setAttribute('aria-label', listening ? 'Stop voice search' : 'Voice search');
    icon.className = listening ? 'bi bi-stop-fill' : 'bi bi-mic';
  }

  // 3: Check Access Permission -> 'granted', 'prompt' or 'denied' ('prompt' when the browser can't say).
  function checkAccessPermission() {
    if (!navigator.permissions || !navigator.permissions.query) return Promise.resolve('prompt');
    return navigator.permissions.query({ name: 'microphone' })
      .then(function (s) { return s.state; }, function () { return 'prompt'; });
  }

  // 4: Request Access Permission: the browser asks the customer; the mic is released straight after.
  function requestAccessPermission() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return Promise.resolve(true);
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      stream.getTracks().forEach(function (t) { t.stop(); });
      return true;
    }, function () { return false; });
  }

  // 10: show recognition error.
  function showRecognitionError(message) {
    failed = true;
    show('Voice search stopped', message, 'is-error');
  }

  // 12: showRecognizedText(text): written into the search box, where the customer can edit it (13).
  function showRecognizedText(text, live) {
    input.value = text;
    mode.value = 'voice';
    if (live) show('Listening… tap the mic again to stop', text || HINT, 'is-live' + (text ? '' : ' is-empty'));
    else show('Got it. Edit it if needed, then press search', text, 'is-done');
  }

  // 5: showRecording() and 6: Record Customer's Voice; 7-8 happen inside the speech service.
  function showRecording() {
    rec = new Rec();
    rec.lang = 'vi-VN'; // shoppers speak Vietnamese; English brand names still come through
    rec.continuous = true;
    rec.interimResults = true;
    kept = ''; failed = false;

    rec.onstart = function () {
      setMic(true);
      show('Listening… tap the mic again to stop', HINT, 'is-live is-empty');
    };
    rec.onresult = function (e) {  // 11: return recognizedText
      var heard = '';
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) kept += e.results[i][0].transcript;
        else heard += e.results[i][0].transcript;
      }
      showRecognizedText((kept + heard).trim(), true);
    };
    rec.onerror = function (e) {  // 9: return error
      var why = {
        'not-allowed': BLOCKED,
        'service-not-allowed': BLOCKED,
        'no-speech': 'No speech heard. Tap the mic and try again.',
        'audio-capture': 'No microphone found.',
        'network': 'Voice search needs an internet connection.'
      }[e.error];
      if (e.error !== 'aborted') showRecognitionError(why || 'Something went wrong. Tap the mic to try again.');
    };
    rec.onend = function () {
      rec = null;
      setMic(false);
      if (failed) return;
      if (input.value.trim()) {
        showRecognizedText(input.value.trim(), false);
        input.focus();
      } else {
        panel.hidden = true;
      }
    };
    try { rec.start(); } catch (err) { rec = null; setMic(false); }
  }

  // 2: open voice search view, then 3-5.
  function openVoiceSearchView() {
    checkAccessPermission().then(function (access) {
      if (access === 'denied') { showRecognitionError(BLOCKED); return; }
      if (access === 'granted') { showRecording(); return; }
      show('Allow the microphone to search by voice', 'Your browser is asking for permission.', 'is-live is-empty');
      requestAccessPermission().then(function (ok) {
        if (ok) showRecording(); else showRecognitionError(BLOCKED);
      });
    });
  }

  // 1: onClickMicrophone; a second click stops listening.
  function onClickMicrophone() {
    if (rec) rec.stop(); else openVoiceSearchView();
  }

  // 13: onEditText(editedText): fixing the recognised words keeps it a voice search; an emptied box is typing.
  function onEditText() {
    if (rec) return;
    if (!input.value.trim()) { mode.value = 'text'; panel.hidden = true; return; }
    if (mode.value !== 'voice') panel.hidden = true;
  }

  // 14: confirmVoiceText(finalText): the form sends q with mode=voice to SearchController.
  function confirmVoiceText() { if (rec) rec.stop(); }

  btn.setAttribute('aria-pressed', 'false');
  btn.addEventListener('click', onClickMicrophone);
  input.addEventListener('input', onEditText);
  form.addEventListener('submit', confirmVoiceText);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && rec) rec.stop(); });
})();
