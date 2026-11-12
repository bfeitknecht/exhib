// Keyboard control for the fullscreen media viewers.
// Left and Right move between items. Escape closes the viewer.
// Space toggles play and pause of the active video.
// A viewer video autoplays while its overlay is open. No dependencies.
(function () {
  var handled = ['ArrowLeft', 'ArrowRight', 'Escape'];
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function openViewer() {
    return document.querySelector('.photo-viewer:target');
  }
  function videos(scope) {
    return scope ? Array.prototype.slice.call(scope.querySelectorAll('video')) : [];
  }
  function overlayVideos() {
    return videos(document).filter(function (video) {
      return !!video.closest('.photo-viewer');
    });
  }
  function play(video) {
    var attempt = video.play();
    if (attempt && typeof attempt.catch === 'function') {
      // Unmuted autoplay can be refused. Retry muted.
      attempt.catch(function () {
        video.muted = true;
        video.play().catch(function () {});
      });
    }
  }
  function stopAutoplay() {
    overlayVideos().forEach(function (video) {
      video.pause();
    });
  }
  // Pause the overlay videos that are not open, then start the open one.
  function syncVideos() {
    var open = openViewer();
    overlayVideos().forEach(function (video) {
      if (!open || !open.contains(video)) video.pause();
    });
    if (reduceMotion.matches) return;
    if (open) videos(open).forEach(play);
  }
  function togglePlay(scope) {
    var media = videos(scope);
    if (!media.length) return false;
    media.forEach(function (video) {
      if (video.paused) { play(video); } else { video.pause(); }
    });
    return true;
  }

  document.addEventListener('hashchange', syncVideos);
  document.addEventListener('keydown', function (event) {
    // Space toggles the video in the open viewer. Native control keys
    // win when a control has the focus, so buttons and links keep
    // their behavior.
    if (event.key === ' ') {
      var onControl = event.target && event.target.closest &&
        event.target.closest('a, button, input, textarea, select, video, audio, [contenteditable]');
      if (onControl) return;
      var open = openViewer();
      if (open && togglePlay(open)) event.preventDefault();
      return;
    }
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

  // If the page opens with an overlay in the URL, start its video.
  syncVideos();
  if (reduceMotion.matches) stopAutoplay();
})();
