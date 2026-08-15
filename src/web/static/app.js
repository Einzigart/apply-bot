// Run form: show only the option fieldset for the selected command.
const runForm = document.getElementById("run-form");
if (runForm) {
  const select = document.getElementById("run-command");
  const sync = () => {
    for (const fs of runForm.querySelectorAll("fieldset[data-cmd]")) {
      const active = fs.dataset.cmd === select.value;
      fs.hidden = !active;
      fs.disabled = !active; // disabled fieldsets do not submit their fields
    }
  };
  select.addEventListener("change", sync);
  sync();

  runForm.addEventListener("submit", (e) => {
    const execute = runForm.querySelector("[name=apply_execute]");
    if (select.value === "apply" && execute && execute.checked &&
        !confirm("This submits REAL applications on Jobstreet. Continue?")) {
      e.preventDefault();
    }
  });
}

// Run detail: poll the log tail every 2s until the run finishes.
const logEl = document.getElementById("run-log");
if (logEl && logEl.dataset.finished !== "1") {
  const stick = () => { logEl.scrollTop = logEl.scrollHeight; };
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/runs/${logEl.dataset.runId}/tail`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.log) { logEl.textContent = data.log; stick(); }
      if (data.finished) {
        clearInterval(timer);
        location.reload(); // re-render the final status header
      }
    } catch {
      // transient fetch error (server restart, sleep) — keep polling
    }
  }, 2000);
}
