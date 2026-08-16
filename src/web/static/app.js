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
    const execute = runForm.querySelector(`[name=${select.value}_execute]`) || runForm.querySelector("[name=apply_execute]");
    if ((select.value === "apply" || select.value === "pipeline") && execute && execute.checked &&
        !confirm("This submits REAL applications on Jobstreet. Continue?")) {
      e.preventDefault();
    }
  });
}

// Jobs page: seamless dynamic table updates without full page refresh flicker
const jobsContainer = document.getElementById("jobs-container");
if (jobsContainer) {
  const updateJobs = async (url, pushHistory = true) => {
    try {
      jobsContainer.style.opacity = "0.7";
      const res = await fetch(url);
      if (!res.ok) throw new Error("fetch failed");
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const newContainer = doc.getElementById("jobs-container");
      if (newContainer) {
        jobsContainer.innerHTML = newContainer.innerHTML;
        if (pushHistory) {
          window.history.pushState({}, "", url);
        }
      }
    } catch {
      window.location.href = url;
    } finally {
      jobsContainer.style.opacity = "1";
    }
  };

  jobsContainer.addEventListener("submit", (e) => {
    if (e.target.id === "jobs-filter-form") {
      e.preventDefault();
      const formData = new FormData(e.target);
      const params = new URLSearchParams();
      for (const [k, v] of formData.entries()) {
        if (v) params.set(k, v);
      }
      const qs = params.toString();
      const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
      updateJobs(url);
    }
  });

  jobsContainer.addEventListener("click", (e) => {
    const sortLink = e.target.closest("a.sort-header");
    const pageLink = e.target.closest(".pagination-controls a.page-btn");
    const pagerLink = e.target.closest(".pager a");
    const targetLink = sortLink || pageLink || pagerLink;
    if (targetLink) {
      e.preventDefault();
      updateJobs(targetLink.href);
    }
  });

  window.addEventListener("popstate", () => {
    if (window.location.pathname === "/jobs") {
      updateJobs(window.location.href, false);
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
