(function () {
  var form = document.getElementById('photo');
  var input = document.getElementById('photo-file');
  if (!form || !input) return;
  var box = document.getElementById('crop-box'), img = document.createElement('img');
  img.alt = 'Your photo, ready to crop';
  document.getElementById('crop-stage').appendChild(img);
  var label = input.nextElementSibling, go = document.getElementById('photo-go');
  var cropper = null, url = null, name = 'photo.jpg';

  input.addEventListener('change', function () {
    var f = input.files[0];
    label.textContent = f ? f.name : 'Choose photo';
    if (cropper) { cropper.destroy(); cropper = null; }
    if (url) { URL.revokeObjectURL(url); url = null; }
    box.hidden = true;
    if (!f || !window.Cropper) return;  // no Cropper: the whole photo is uploaded as before
    name = f.name.replace(/\.[^.]+$/, '') + '.jpg';
    url = URL.createObjectURL(f);
    img.onload = function () {
      box.hidden = false;
      cropper = new Cropper(img, { viewMode: 1, autoCropArea: 0.9, background: false, responsive: true });
    };
    img.src = url;
  });

  document.getElementById('crop-reset').addEventListener('click', function () { if (cropper) cropper.reset(); });

  // The AI can take half a minute to look at a photo, so say so while the page waits.
  function busy() {
    go.disabled = true;
    go.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>AI is looking at your photo…';
  }

  // Coming back with the Back button must not leave the button stuck on "looking".
  window.addEventListener('pageshow', function () { go.disabled = false; go.textContent = 'Search'; delete form.dataset.cropped; });

  form.addEventListener('submit', function (e) {
    if (!input.files.length) return;
    busy();
    if (!cropper || form.dataset.cropped) return;
    e.preventDefault();
    var canvas = cropper.getCroppedCanvas({ maxWidth: 1024, maxHeight: 1024, fillColor: '#fff' });
    if (!canvas) { form.submit(); return; }
    canvas.toBlob(function (blob) {
      var dt = new DataTransfer();
      dt.items.add(new File([blob], name, { type: 'image/jpeg' }));
      input.files = dt.files;
      form.dataset.cropped = '1';
      form.submit();
    }, 'image/jpeg', 0.9);
  });
})();
