const $ = (id) => document.getElementById(id);

function metric(label, value) {
  return `<div class="metric"><span class="label">${label}</span><b>${value}</b></div>`;
}

async function getJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function bust(url) {
  return `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
}

async function loadStatus() {
  const status = await getJson("/api/status");
  $("station").textContent = status.station;
  $("operator").textContent = `${status.operator} · ${status.demo_mode ? "demo simulator" : "live inbox"}`;
  $("utc").textContent = status.utc.replace("T", " ").replace("+00:00", "");
  document.title = status.station;
  $("metrics").innerHTML = [
    metric("Sun alt", `${status.sun_alt.toFixed(1)}°`),
    metric("Sun az", `${status.sun_az.toFixed(1)}°`),
    metric("Sky", status.is_night ? "Night" : "Day"),
    metric("Moon", `${Math.round(status.moon_illumination * 100)}%`),
    metric("Phase", status.moon_phase),
    metric("Site", `${status.latitude.toFixed(2)}, ${status.longitude.toFixed(2)}`),
  ].join("");

  const daySelect = $("day");
  const previous = daySelect.value;
  daySelect.innerHTML = status.days
    .slice()
    .reverse()
    .map((day) => `<option value="${day}">${day}</option>`)
    .join("");
  if (previous && status.days.includes(previous)) {
    daySelect.value = previous;
  }
  $("latest").src = bust("/api/latest");
  const latest = status.latest || {};
  $("latest-caption").textContent = latest.captured_at
    ? `last frame ${latest.captured_at.replace("T", " ")}`
    : "no frames yet";
  return status;
}

async function loadNight(day) {
  if (!day) return;
  $("keogram").src = bust(`/api/keogram?day=${day}`);
  $("startrails").src = bust(`/api/startrails?day=${day}`);
  const archive = await getJson(`/api/archive?day=${day}`);
  $("archive").innerHTML = archive.frames
    .map((src) => `<img src="${src}" alt="" />`)
    .join("");
}

async function refresh() {
  const status = await loadStatus();
  await loadNight($("day").value || status.days.at(-1));
}

$("day").addEventListener("change", () => loadNight($("day").value));

$("capture").addEventListener("click", async () => {
  await getJson("/api/capture", { method: "POST" });
  await refresh();
});

$("rebuild").addEventListener("click", async () => {
  const day = $("day").value;
  if (!day) return;
  await getJson(`/api/products?day=${day}`, { method: "POST" });
  await loadNight(day);
});

refresh();
setInterval(loadStatus, 15000);
