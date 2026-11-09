// Keyboard navigation for the CSS :target media viewers on collection pages.
// Left/Right move between items; Escape closes back to the grid.
// No dependencies; only active while a #photo-* overlay is open.
(function () {
  var handled = ['ArrowLeft', 'ArrowRight', 'Escape'];
  document.addEventListener('keydown', function (event) {
    if (handled.indexOf(event.key) === -1) return;
    var match = location.hash.match(/^#photo-(\d+)$/);
    if (!match) return;
    event.preventDefault();
    if (event.key === 'Escape') {
      location.hash = 'gallery';
      return;
    }
    var total = document.querySelectorAll('.photo-viewer[id^="photo-"]').length;
    var next = parseInt(match[1], 10) + (event.key === 'ArrowRight' ? 1 : -1);
    // Clamp at the ends to match the disabled << / >> chrome.
    if (next < 1 || next > total) return;
    location.hash = 'photo-' + String(next).padStart(2, '0');
  });
})();
