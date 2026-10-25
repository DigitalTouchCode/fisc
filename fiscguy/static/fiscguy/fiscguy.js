(function () {
  "use strict";

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  var ping = document.getElementById("ping");
  if (ping) {
    fetch(ping.getAttribute("data-ping-url"), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        ping.textContent = data.online ? "online" : "offline";
        ping.className = "pill " + (data.online ? "online" : "offline");
      })
      .catch(function () {
        ping.textContent = "offline";
        ping.className = "pill offline";
      });
  }

  var dayState = document.getElementById("day-state");
  var pollUrl = dayState && dayState.getAttribute("data-poll-url");
  if (pollUrl) {
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1;
      fetch(pollUrl, { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.close_state && data.close_state !== "close_pending") {
            window.clearInterval(timer);
            window.location.reload();
          }
        })
        .catch(function () {});
      if (attempts >= 60) {
        window.clearInterval(timer);
      }
    }, 5000);
  }
})();
