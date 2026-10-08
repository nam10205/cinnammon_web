(function () {
  var root = document.getElementById('mx-assistant');
  if (!root) return;
  var panel = root.querySelector('.mx-assistant-panel');
  var toggle = root.querySelector('.mx-assistant-toggle');
  var log = root.querySelector('.mx-assistant-log');
  var form = root.querySelector('.mx-assistant-form');
  var input = form.querySelector('input');
  var KEY = 'mx-assistant-history', OPEN = 'mx-assistant-open';
  var history = [];
  try { history = JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch (e) { history = []; }

  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(history.slice(-20))); } catch (e) {} }
  function escapeHtml(s) { return s.replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function format(text) {
    var html = escapeHtml(text).replace(/^\s*[*-]\s+/gm, '• ');
    html = html.replace(/\[([^\]]+)\]\((\/[^)\s]*)\)/g, '<a href="$2">$1</a>');   // only local links
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    return html.replace(/\n/g, '<br>');
  }
  function bubble(role, text, extra) {
    var d = document.createElement('div');
    d.className = 'mx-msg mx-msg-' + role + (extra ? ' ' + extra : '');
    d.innerHTML = format(text);
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }
  function render() {
    log.innerHTML = '';
    bubble('model', 'Hi! I can help you find products, explain vouchers, shipping and returns, or check your orders.');
    history.forEach(function (h) { bubble(h.role, h.text); });
  }
  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    try { sessionStorage.setItem(OPEN, open ? '1' : ''); } catch (e) {}
    if (open) { log.scrollTop = log.scrollHeight; input.focus(); }
  }

  toggle.addEventListener('click', function () { setOpen(panel.hidden); });
  root.querySelector('.mx-assistant-close').addEventListener('click', function () { setOpen(false); toggle.focus(); });
  root.querySelector('.mx-assistant-clear').addEventListener('click', function () { history = []; save(); render(); });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    bubble('user', msg);
    var typing = bubble('model', '…', 'mx-typing');
    var sent = history.slice(-10);
    fetch('/api/assistant', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, history: sent }) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        typing.remove();
        if (res.ok) {
          history.push({ role: 'user', text: msg }, { role: 'model', text: res.j.reply });
          save();
          bubble('model', res.j.reply);
        } else {
          bubble('model', res.j.message || 'Something went wrong.', 'mx-error');
        }
      })
      .catch(function () { typing.remove(); bubble('model', 'Network error — please try again.', 'mx-error'); });
  });

  render();
  var wasOpen = false;
  try { wasOpen = !!sessionStorage.getItem(OPEN); } catch (e) {}
  setOpen(wasOpen);
})();
