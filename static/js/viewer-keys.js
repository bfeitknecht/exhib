// Home page videos autoplay unless the user prefers reduced motion.
// Left and Right move between items in the fullscreen viewers.
// Escape closes the viewer. No dependencies.
(function () {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!reduceMotion.matches) {
    // Silent inline loops on the feed. No controls, no audio.
    Array.prototype.forEach.call(document.querySelectorAll('.item-preview video[data-autoplay]'), function (video) {
      var attempt = video.play();
      if (attempt && typeof attempt.catch === 'function') attempt.catch(function () {});
    });
  }

  var handled = ['ArrowLeft', 'ArrowRight', 'Escape'];
  document.addEventListener('keydown', function (event) {
    if (handled.indexOf(event.key) === -1) return;
    if (event.key === 'Escape') {
      if (location.hash === '#piece-detail') {
        event.preventDefault();
        location.hash = 'piece-main';
      } else if (/^#photo-\d+$/.test(location.hash)) {
        event.preventDefault();
        location.hash = 'gallery';
      }
      return;
    }
    var match = location.hash.match(/^#photo-(\d+)$/);
    if (!match) return;
    event.preventDefault();
    var total = document.querySelectorAll('.photo-viewer[id^="photo-"]').length;
    var next = parseInt(match[1], 10) + (event.key === 'ArrowRight' ? 1 : -1);
    // Stop at the ends, like the disabled << and >> controls.
    if (next < 1 || next > total) return;
    location.hash = 'photo-' + String(next).padStart(2, '0');
  });
})();
