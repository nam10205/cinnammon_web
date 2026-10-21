(function () {
  var form = document.querySelector('.shell-search');
  if (!form) return;
  var input = form.elements['q'], mode = form.elements['mode'], mic = document.getElementById('mic');

  // Recent searches under the box, like a search engine: shown on focus, filtered while typing.
  var list = document.createElement('ul');
  list.className = 'search-recent';
  list.id = 'search-recent';
  list.setAttribute('role', 'listbox');
  list.setAttribute('aria-label', 'Recent searches');
  list.hidden = true;
  form.appendChild(list);
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-controls', 'search-recent');
  input.setAttribute('aria-expanded', 'false');
  input.setAttribute('autocomplete', 'off');

  var items = null, shown = [], active = -1, loading = null;

  // Accent-blind matching so "quan" finds "quần áo"; one letter in, one letter out, so positions line up.
  function fold(s) {
    return s.normalize('NFC').toLowerCase().split('').map(function (ch) {
      return ch === 'đ' ? 'd' : ch.normalize('NFD').charAt(0);
    }).join('');
  }

  function load() {
    if (items) return Promise.resolve(items);
    if (!loading) {
      loading = fetch('/api/search/history', { headers: { Accept: 'application/json' } })
        .then(function (r) { return r.ok ? r.json() : { items: [] }; })
        .then(function (d) { items = d.items || []; return items; })
        .catch(function () { items = []; return items; });
    }
    return loading;
  }

  function close() {
    list.hidden = true;
    active = -1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function render() {
    var typed = fold(input.value.trim());
    shown = items.filter(function (it) { return !typed || fold(it.q).indexOf(typed) !== -1; })
                 .filter(function (it) { return fold(it.q) !== typed; });
    list.textContent = '';
    if (!shown.length || (mic && mic.classList.contains('listening'))) { close(); return; }
    list.appendChild(el('li', 'search-recent-head', 'Recent searches')).setAttribute('role', 'presentation');
    shown.forEach(function (it, i) {
      var li = el('li', 'search-recent-item');
      li.id = 'search-recent-' + i;
      li.setAttribute('role', 'option');
      li.appendChild(el('i', 'bi bi-' + (it.type === 'voice' ? 'mic' : 'clock-history'))).setAttribute('aria-hidden', 'true');
      var text = el('span', 'search-recent-text');
      var q = it.q.normalize('NFC'), at = typed ? fold(q).indexOf(typed) : -1;
      if (at >= 0) {
        text.appendChild(document.createTextNode(q.slice(0, at)));
        text.appendChild(el('b', '', q.slice(at, at + typed.length)));
        text.appendChild(document.createTextNode(q.slice(at + typed.length)));
      } else {
        text.textContent = it.q;
      }
      li.appendChild(text);
      li.addEventListener('mousedown', function (e) { e.preventDefault(); });  // keep focus in the box
      li.addEventListener('click', function () { pick(i); });
      list.appendChild(li);
    });
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    highlight(-1);
  }

  function highlight(i) {
    active = i;
    list.querySelectorAll('.search-recent-item').forEach(function (li, n) {
      li.classList.toggle('is-active', n === i);
      li.setAttribute('aria-selected', n === i ? 'true' : 'false');
    });
    if (i >= 0) input.setAttribute('aria-activedescendant', 'search-recent-' + i);
    else input.removeAttribute('aria-activedescendant');
  }

  function pick(i) {
    input.value = shown[i].q;
    mode.value = 'text';
    close();
    form.submit();
  }

  function open() { load().then(function () { if (document.activeElement === input) render(); }); }

  input.addEventListener('focus', open);
  input.addEventListener('click', open);
  input.addEventListener('input', function () { if (items) render(); else open(); });
  input.addEventListener('blur', close);
  input.addEventListener('keydown', function (e) {
    if (list.hidden) {
      if (e.key === 'ArrowDown') { open(); e.preventDefault(); }
      return;
    }
    if (e.key === 'ArrowDown') { highlight((active + 1) % shown.length); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { highlight(active <= 0 ? shown.length - 1 : active - 1); e.preventDefault(); }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(active); }
    else if (e.key === 'Escape') { close(); }
  });
  if (mic) mic.addEventListener('click', close);
})();
