(() => {
  "use strict";
  fetch("/data-status.json", {cache: "no-store"})
    .then(response => response.ok ? response.json() : null)
    .then(status => {
      const target = document.getElementById("dataFreshness");
      if (target && status && /^\d{4}-\d{2}-\d{2}$/.test(status.latest_observation)) {
        target.textContent = "Latest observation: " + status.latest_observation + " · Checked daily · ";
      }
    }).catch(() => {});
})();
