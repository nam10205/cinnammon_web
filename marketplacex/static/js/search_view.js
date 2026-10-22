// SearchView from the keyword search diagram: the header search box, its recent-history dropdown
// (steps 1-6), the keyword check before submitting (7-11) and the error popup the other views share.
(function () {
  var MAX_KEYWORD = 100;
  // Same blocks as the server's EMOJI_RE, so the browser and the server agree on what is refused.
  var EMOJI = /[\u{1F000}-\u{1FAFF}\u{2300}-\u{23FF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{200D}\u{FE0F}\u{20E3}]/u;
  var LETTER = /[\p{L}\p{N}]/u;
  var modal = null, afterClose = null;

  // showError(title, message): a small centred popup; OK puts the cursor back where the customer was.
  function showError(title, message, onClose) {
    if (!modal) {
      var el = document.createElement('div');
      el.className = 'modal fade';
      el.tabIndex = -1;
      el.setAttribute('aria-labelledby', 'popup-error-title');
      el.innerHTML =
        '<div class="modal-dialog modal-dialog-centered modal-sm"><div class="modal-content">' +
        '<div class="modal-body text-center p-4">' +
        '<i class="bi bi-exclamation-circle fs-2 text-danger" aria-hidden="true"></i>' +
        '<h2 class="h6 mt-2 mb-1" id="popup-error-title"></h2>' +
        '<p class="hint mb-3" id="popup-error-text"></p>' +
        '<button type="button" class="btn btn-primary w-100" data-bs-dismiss="modal">OK</button>' +
        '</div></div></div>';
      document.body.appendChild(el);
      el.addEventListener('hidden.bs.modal', function () { if (afterClose) afterClose(); });
      modal = { el: el, bs: window.bootstrap ? new bootstrap.Modal(el) : null };
    }
    afterClose = onClose || null;
    modal.el.querySelector('#popup-error-title').textContent = title;
    modal.el.querySelector('#popup-error-text').textContent = message;
    if (modal.bs) modal.bs.show(); else { alert(title + '\n' + message); if (afterClose) afterClose(); }
  }
  window.searchView = { showError: showError };

  var form = document.querySelector('.shell-search');
  var input = form && form.elements['q'];
  function backToBox() { if (input) { input.focus(); input.select(); } }

  // The server refused something (bad keyword, bad photo): show its message the same way.
  var served = document.getElementById('popup-error');
  if (served) showError(served.dataset.title, served.dataset.message, backToBox);

  if (!form) return;
  var mode = form.elements['mode'], mic = document.getElementById('mic');

  // 9: validateKeyword(), mirrored from SearchController so a bad keyword never leaves the page.
  function validateKeyword(keyword) {
    keyword = keyword.trim();
    if (!keyword) return 'Type a product name or brand to search.';
    if (keyword.length > MAX_KEYWORD) return 'Keep your search under ' + MAX_KEYWORD + ' characters.';
    if (EMOJI.test(keyword)) return "Search can't contain emojis. Please use letters and numbers only.";
    if (!LETTER.test(keyword)) return 'Use letters or numbers to search.';
    return null;
  }

  // 7-8: submit query -> searchByKeyword(keyword), or 11: showError("Invalid Keyword").
  form.addEventListener('submit', function (e) {
    var problem = validateKeyword(input.value);
    if (!problem) return;
    e.preventDefault();
    showError('Invalid Keyword', problem, backToBox);
  });

  // 1-6: selecting the box shows the customer's recent keywords, filtered while typing.
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

  // 2-5: showSearchBox(customerId) -> SearchController -> SearchHistoryDAO.findRecent -> listHistory.
  function showSearchBox() {
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

  // 6: show recent history.
  function showRecentHistory() {
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

  // 1: selectKeywordSearchBar.
  function selectKeywordSearchBar() {
    showSearchBox().then(function () { if (document.activeElement === input) showRecentHistory(); });
  }

  input.addEventListener('focus', selectKeywordSearchBar);
  input.addEventListener('click', selectKeywordSearchBar);
  input.addEventListener('input', function () { if (items) showRecentHistory(); else selectKeywordSearchBar(); });
  input.addEventListener('blur', close);
  input.addEventListener('keydown', function (e) {
    if (list.hidden) {
      if (e.key === 'ArrowDown') { selectKeywordSearchBar(); e.preventDefault(); }
      return;
    }
    if (e.key === 'ArrowDown') { highlight((active + 1) % shown.length); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { highlight(active <= 0 ? shown.length - 1 : active - 1); e.preventDefault(); }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(active); }
    else if (e.key === 'Escape') { close(); }
  });
  if (mic) mic.addEventListener('click', close);
})();
