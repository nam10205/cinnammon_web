// ImageSearchView from the image search diagram: pick a photo, let SearchController validate it,
// mark the product on it, then searchByImage(image, region). The region travels as x, y, width, height.
(function () {
  var form = document.getElementById('photo');
  var input = document.getElementById('photo-file');
  if (!form || !input) return;
  var box = document.getElementById('crop-box'), img = document.createElement('img');
  img.alt = 'Your photo, ready to crop';
  document.getElementById('crop-stage').appendChild(img);
  var label = input.nextElementSibling, go = document.getElementById('photo-go');
  var MAX_SIDE = 1600, MAX_BYTES = 5 * 1024 * 1024;
  var cropper = null, url = null, photo = null;  // photo: the File that will be searched

  var region = {};
  ['x', 'y', 'width', 'height'].forEach(function (k) {
    var h = document.createElement('input');
    h.type = 'hidden';
    h.name = k;
    form.appendChild(h);
    region[k] = h;
  });

  function showError(message) {
    var title = 'File error';
    if (window.searchView) window.searchView.showError(title, message); else alert(title + ': ' + message);
  }

  function reset() {
    if (cropper) { cropper.destroy(); cropper = null; }
    if (url) { URL.revokeObjectURL(url); url = null; }
    box.hidden = true;
    photo = null;
  }

  // Phone photos can be larger than the 5 MB upload limit, so a big picture is scaled down first.
  function shrink(file) {
    return new Promise(function (resolve) {
      var probe = new Image(), src = URL.createObjectURL(file);
      probe.onload = function () {
        URL.revokeObjectURL(src);
        var scale = Math.min(1, MAX_SIDE / Math.max(probe.naturalWidth, probe.naturalHeight));
        if (scale === 1 && file.size <= MAX_BYTES) { resolve(file); return; }
        var c = document.createElement('canvas');
        c.width = Math.round(probe.naturalWidth * scale);
        c.height = Math.round(probe.naturalHeight * scale);
        var ctx = c.getContext('2d');
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(probe, 0, 0, c.width, c.height);
        c.toBlob(function (blob) {
          resolve(new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' }));
        }, 'image/jpeg', 0.9);
      };
      probe.onerror = function () { URL.revokeObjectURL(src); resolve(file); };  // let the server judge it
      probe.src = src;
    });
  }

  // 5-11: imageFile -> SearchController.validateImage() -> "File error" or the image back.
  function validateImage(file) {
    if (file.size > MAX_BYTES) return Promise.resolve('That photo is over 5 MB.');
    var data = new FormData();
    data.append('photo', file);
    return fetch('/api/search/image/validate', { method: 'POST', body: data })
      .then(function (r) { return r.json(); })
      .then(function (d) { return d.ok ? null : d.error; })
      .catch(function () { return null; });  // offline check: the search itself validates again
  }

  // 12-13: show the image and let the customer mark the target object.
  function showImage(file) {
    photo = file;
    url = URL.createObjectURL(file);
    img.onload = function () {
      box.hidden = false;
      if (window.Cropper) {
        cropper = new Cropper(img, { viewMode: 1, autoCropArea: 0.9, background: false, responsive: true,
                                     checkOrientation: false });
      }
    };
    img.src = url;
  }

  // 4: submit product image.
  input.addEventListener('change', function () {
    var f = input.files[0];
    reset();
    label.textContent = f ? f.name : 'Choose photo';
    if (!f) return;
    go.disabled = true;
    shrink(f).then(function (small) {
      return validateImage(small).then(function (problem) {
        go.disabled = false;
        if (problem) { input.value = ''; label.textContent = 'Choose photo'; showError(problem); return; }
        showImage(small);
      });
    });
  });

  document.getElementById('crop-reset').addEventListener('click', function () { if (cropper) cropper.reset(); });

  // 1-2: onClickCamera -> showImagePicker(), when the camera button is pressed on this page.
  var camera = document.getElementById('camera');
  if (camera) camera.addEventListener('click', function (e) { e.preventDefault(); input.click(); });

  // The AI can take half a minute to look at a photo, so say so while the page waits.
  function busy() {
    go.disabled = true;
    go.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>AI is looking at your photo…';
  }

  // Coming back with the Back button must not leave the button stuck on "looking".
  window.addEventListener('pageshow', function () { go.disabled = false; go.textContent = 'Search'; delete form.dataset.ready; });

  // 14: searchByImage(image, region).
  form.addEventListener('submit', function (e) {
    if (!input.files.length) { e.preventDefault(); showError('Choose a photo to search with.'); return; }
    if (!photo || form.dataset.ready) { busy(); return; }  // no script help: the whole photo goes as chosen
    e.preventDefault();
    var r = cropper ? cropper.getData(true) : null;
    ['x', 'y', 'width', 'height'].forEach(function (k) { region[k].value = r ? r[k] : ''; });
    var dt = new DataTransfer();
    dt.items.add(photo);
    input.files = dt.files;
    form.dataset.ready = '1';
    busy();
    form.submit();
  });
})();
