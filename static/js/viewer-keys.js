// Left and Right move between items in the fullscreen viewers.
// Escape closes the viewer. A hash change pauses videos that left view.
// Feed videos autoplay muted through the markup. No dependencies.
(function () {
  var handled = ["ArrowLeft", "ArrowRight", "Escape"];
  document.addEventListener("keydown", function (event) {
    if (handled.indexOf(event.key) === -1) return;
    if (event.key === "Escape") {
      if (location.hash === "#piece-detail") {
        event.preventDefault();
        location.hash = "piece-main";
      } else if (/^#photo-\d+$/.test(location.hash)) {
        event.preventDefault();
        location.hash = "gallery";
      }
      return;
    }
    var match = location.hash.match(/^#photo-(\d+)$/);
    if (!match) return;
    event.preventDefault();
    var total = document.querySelectorAll('.photo-viewer[id^="photo-"]').length;
    var next = parseInt(match[1], 10) + (event.key === "ArrowRight" ? 1 : -1);
    // Stop at the ends, like the disabled << and >> controls.
    if (next < 1 || next > total) return;
    location.hash = "photo-" + String(next).padStart(2, "0");
  });

  // The viewers are :target overlays. A hash change hides the old overlay
  // but does not stop its video. Pause every viewer video outside the new
  // target, so the sound stops on next, previous, close and browser back.
  // Muted grid previews have no controls and keep looping.
  window.addEventListener("hashchange", function () {
    var id = location.hash.slice(1);
    var target = id ? document.getElementById(id) : null;
    document.querySelectorAll("video[controls]").forEach(function (video) {
      if (!video.paused && !(target && target.contains(video))) video.pause();
    });
  });
})();
