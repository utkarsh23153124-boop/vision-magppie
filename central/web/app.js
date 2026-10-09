"use strict";
const $ = (id) => document.getElementById(id);
let csrf = null,
  refreshing = false;
const notify = (text) => {
  $("notice").textContent = text;
};
function textCell(row, text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  row.append(cell);
  return cell;
}
function button(parent, label, action) {
  const b = document.createElement("button");
  b.textContent = label;
  b.onclick = async () => {
    b.disabled = true;
    b.classList.add("loading");
    const original = b.textContent;
    if (label === "Start") b.textContent = "Starting…";
    else if (label === "Stop") b.textContent = "Stopping…";
    else if (label === "Remove") b.textContent = "Removing…";
    try {
      await action();
      await refresh();
    } catch (e) {
      notify(e.message);
    } finally {
      b.classList.remove("loading");
      b.textContent = original;
      b.disabled = false;
    }
  };
  parent.append(b);
}
async function api(path, data) {
  const response = await fetch(
    path,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf || "",
          },
          body: JSON.stringify(data),
        },
  );
  const result = await response.json();
  if (response.status === 401) {
    showLogin();
    throw Error("Please sign in.");
  }
  if (!response.ok) throw Error(result.error || "Request failed.");
  return result;
}
function showLogin() {
  csrf = null;
  $("dashboard").hidden = true;
  $("login").hidden = false;
  $("logout").hidden = true;
}
async function session() {
  const result = await api("/api/session");
  csrf = result.csrf;
  $("dashboard").hidden = false;
  $("login").hidden = true;
  $("logout").hidden = false;
  await refresh();
}
$("date").value = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Kolkata",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}).format(new Date());
$("date").onchange = () => refresh();
$("loginForm").onsubmit = async (event) => {
  event.preventDefault();
  try {
    await api("/api/login", { password: $("password").value });
    $("password").value = "";
    notify("");
    await session();
  } catch (e) {
    notify(e.message);
  }
};
$("logout").onclick = async () => {
  try {
    await api("/api/logout", {});
    showLogin();
  } catch (e) {
    notify(e.message);
  }
};
$("cameraForm").onsubmit = async (event) => {
  event.preventDefault();
  try {
    await api("/api/cameras", {
      showroom: $("showroom").value,
      name: $("cameraName").value,
      source_ref: $("sourceRef").value,
      axis: $("axis").value,
      position: Number($("position").value) / 100,
      in_positive: $("direction").value === "positive",
      zone_mode: $("zoneMode").checked,
    });
    notify(
      "Camera added. Configure its stream secret on the server, then press Start.",
    );
    await refresh();
  } catch (e) {
    notify(e.message);
  }
};
function readPhoto(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(Error("Could not read photo."));
    reader.readAsDataURL(file);
  });
}
$("staffForm").onsubmit = async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const files = [...$("photos").files];
    if (
      !files.length ||
      files.length > 10 ||
      files.reduce((n, f) => n + f.size, 0) > 12_000_000
    )
      throw Error("Choose 1–10 portraits, under 12 MB total.");
    notify("Processing staff portraits…");
    await api("/api/staff", {
      showroom: $("staffShowroom").value,
      name: $("staffName").value,
      consent: $("consent").checked,
      photos: await Promise.all(files.map(readPhoto)),
    });
    $("staffForm").reset();
    notify("Staff enrolled. Verify exclusion on a real entrance walkthrough.");
    await refresh();
  } catch (e) {
    notify(e.message);
  } finally {
    submit.disabled = false;
  }
};
$("uniformForm").onsubmit = async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const files = [...$("uniformPhotos").files];
    if (!files.length || files.length > 10)
      throw Error("Choose 1–10 uniform sample photos.");
    notify("Calculating uniform color histogram…");
    await api("/api/uniform", {
      showroom: $("uniformShowroom").value,
      label: $("uniformLabel").value,
      photos: await Promise.all(files.map(readPhoto)),
    });
    $("uniformForm").reset();
    notify("Uniform registered successfully.");
    await refresh();
  } catch (e) {
    notify(e.message);
  } finally {
    submit.disabled = false;
  }
};
// Tab switching
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    const target = $(btn.dataset.tab);
    if (target) target.classList.add("active");
  };
});

function formatIST(isoString) {
  if (!isoString) return "-";
  try {
    return new Date(isoString).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      dateStyle: "short",
      timeStyle: "medium",
    });
  } catch {
    return isoString;
  }
}

async function refresh() {
  if (!csrf || refreshing) return;
  refreshing = true;
  try {
    const data = await api(
      "/api/dashboard?date=" + encodeURIComponent($("date").value),
    );
    $("export").href =
      "/api/report.csv?date=" + encodeURIComponent($("date").value);
    const totals = data.report.cameras.reduce(
      (a, r) => ({
        entries: a.entries + r.entries,
        exits: a.exits + r.exits,
        excluded: a.excluded + r.staff_excluded,
      }),
      { entries: 0, exits: 0, excluded: 0 },
    );
    for (const key of ["entries", "exits", "excluded"])
      $(key).textContent = totals[key];
    $("connected").textContent = Object.values(data.workers).filter(
      (w) =>
        w.state === "connected" &&
        w.worker_alive &&
        w.result_age_seconds !== null &&
        w.result_age_seconds < 5,
    ).length;

    // Render Overview Cameras
    if ($("camerasOverview")) {
      $("camerasOverview").replaceChildren();
      for (const camera of data.cameras) {
        const w = data.workers[camera.id] || {},
          r = data.report.cameras.find((r) => r.camera_id === camera.id) || {};
        const row = document.createElement("tr");
        textCell(row, camera.showroom + " / " + camera.name);
        const srcCell = textCell(row, "");
        const span = document.createElement("span");
        span.className = "badge-stream";
        span.textContent = camera.source_ref;
        srcCell.append(span);
        textCell(
          row,
          w.state || (camera.enabled ? "Restart pending" : "Stopped"),
        );
        textCell(row, `${r.entries || 0} / ${r.exits || 0}`);
        textCell(row, r.staff_excluded || 0);
        textCell(
          row,
          `${w.ai_fps || 0} FPS · ${w.result_age_seconds == null ? "no result" : w.result_age_seconds + "s ago"}`,
        );
        const actions = textCell(row, "");
        button(actions, "Start", () =>
          api("/api/cameras/start", { id: camera.id }),
        );
        button(actions, "Stop", () =>
          api("/api/cameras/stop", { id: camera.id }),
        );
        button(actions, "Preview", async () => {
          selectedCamera = camera.id;
          $("previewPanel").hidden = false;
          // Switch to cameras tab to view preview
          document.querySelector('[data-tab="tab-cameras"]')?.click();
        });
        $("camerasOverview").append(row);
      }
    }

    // Render Configured Cameras (Tab 2)
    $("cameras").replaceChildren();
    $("empty").hidden = data.cameras.length > 0;
    for (const camera of data.cameras) {
      const w = data.workers[camera.id] || {},
        r = data.report.cameras.find((r) => r.camera_id === camera.id) || {};
      const row = document.createElement("tr");
      textCell(row, camera.showroom + " / " + camera.name);
      const srcCell = textCell(row, "");
      const span = document.createElement("span");
      span.className = "badge-stream";
      span.textContent = camera.source_ref;
      srcCell.append(span);
      textCell(
        row,
        w.state || (camera.enabled ? "Restart pending" : "Stopped"),
      );
      textCell(row, `${r.entries || 0} / ${r.exits || 0}`);
      textCell(row, r.staff_excluded || 0);
      textCell(
        row,
        `${w.ai_fps || 0} FPS · ${w.result_age_seconds == null ? "no result" : w.result_age_seconds + "s ago"}`,
      );
      const actions = textCell(row, "");
      button(actions, "Start", () =>
        api("/api/cameras/start", { id: camera.id }),
      );
      button(actions, "Stop", () =>
        api("/api/cameras/stop", { id: camera.id }),
      );
      button(actions, "Set line", async () => {
        editingCamera = camera.id;
        $("linePanel").hidden = false;
        $("lineCamera").textContent = camera.showroom + " / " + camera.name;
        $("lineAxis").value = camera.axis;
        $("linePosition").value = camera.position * 100;
        $("lineDirection").value = camera.in_positive ? "positive" : "negative";
        $("lineZoneMode").checked = !!camera.zone_mode;
      });
      button(actions, "Preview", async () => {
        selectedCamera = camera.id;
        $("previewPanel").hidden = false;
      });
      button(actions, "Remove", async () => {
        if (confirm(`Remove camera "${camera.name}" (${camera.showroom})?`)) {
          await api("/api/cameras/delete", { id: camera.id });
        }
      });
      $("cameras").append(row);
    }

    // Render Enrolled Staff (Tab 3)
    $("staff").replaceChildren();
    const staffList = data.staff || [];
    if ($("staffEmpty")) $("staffEmpty").hidden = staffList.length > 0;
    const staffTitle = document.querySelector("#tab-staff .panel:first-child h2");
    if (staffTitle) staffTitle.textContent = `Enrolled staff members (${staffList.length})`;
    for (const staff of staffList) {
      const row = document.createElement("div");
      row.className = "staff-item";
      const info = document.createElement("div");
      info.style.display = "flex";
      info.style.flexDirection = "column";
      info.style.gap = "4px";

      const header = document.createElement("div");
      header.style.display = "flex";
      header.style.alignItems = "center";
      header.style.gap = "8px";
      header.innerHTML = `<strong>👤 ${staff.name}</strong> <span class="badge-tag badge-staff">Face Enrolled</span>`;
      
      const sub = document.createElement("div");
      sub.className = "muted";
      sub.style.fontSize = "12px";
      sub.textContent = `Showroom: ${staff.showroom} · Enrolled: ${formatIST(staff.consent_at)}`;

      info.append(header, sub);
      row.append(info);

      button(row, "Remove", async () => {
        if (confirm("Delete face templates for " + staff.name + "?")) {
          await api("/api/staff/delete", { id: staff.id });
          await refresh();
        }
      });
      $("staff").append(row);
    }

    // Render Uniforms (Tab 3)
    $("uniforms").replaceChildren();
    const uniformList = data.uniforms || [];
    if ($("uniformEmpty")) $("uniformEmpty").hidden = uniformList.length > 0;
    const uniformTitle = document.querySelector("#tab-staff .panel:nth-child(2) h2");
    if (uniformTitle) uniformTitle.textContent = `Staff uniform color profiles (${uniformList.length})`;
    for (const u of uniformList) {
      const row = document.createElement("div");
      row.className = "staff-item";
      const info = document.createElement("div");
      info.style.display = "flex";
      info.style.flexDirection = "column";
      info.style.gap = "4px";

      const header = document.createElement("div");
      header.style.display = "flex";
      header.style.alignItems = "center";
      header.style.gap = "8px";
      header.innerHTML = `<strong>👔 ${u.label}</strong> <span class="badge-tag badge-stream">HSV Profile</span>`;

      const sub = document.createElement("div");
      sub.className = "muted";
      sub.style.fontSize = "12px";
      sub.textContent = `Showroom: ${u.showroom} · Registered: ${formatIST(u.created_at)}`;

      info.append(header, sub);
      row.append(info);

      button(row, "Remove", async () => {
        if (confirm("Delete uniform " + u.label + "?")) {
          await api("/api/uniform/delete", {
            showroom: u.showroom,
            label: u.label,
          });
          await refresh();
        }
      });
      $("uniforms").append(row);
    }

    // Render Hourly Crossings
    $("hours").replaceChildren();
    for (const hour of data.report.hours) {
      const row = document.createElement("tr");
      textCell(row, String(hour.hour).padStart(2, "0") + ":00");
      textCell(row, hour.entries);
      textCell(row, hour.exits);
      $("hours").append(row);
    }

    // Render Staff History Log (Tab 4)
    if ($("staffHistory")) {
      $("staffHistory").replaceChildren();
      const staffHistoryList = data.staff_history || [];
      if ($("staffHistoryEmpty")) $("staffHistoryEmpty").hidden = staffHistoryList.length > 0;
      for (const item of staffHistoryList) {
        const row = document.createElement("tr");
        textCell(row, formatIST(item.observed_at));
        textCell(row, item.showroom || "-");
        textCell(row, item.camera_name || item.camera_id);
        const idCell = textCell(row, "");
        const idSpan = document.createElement("span");
        idSpan.style.fontWeight = "600";
        idSpan.textContent = `👤 ${item.staff_name || "Enrolled Staff"}`;
        idCell.append(idSpan);
        const dirCell = textCell(row, "");
        const dirSpan = document.createElement("span");
        dirSpan.className = item.direction === "IN" ? "badge-in" : "badge-out";
        dirSpan.textContent = item.direction;
        dirCell.append(dirSpan);
        const catCell = textCell(row, "");
        const catBadge = document.createElement("span");
        catBadge.className = "badge-tag badge-staff";
        catBadge.textContent = "STAFF EXCLUDED";
        catCell.append(catBadge);
        $("staffHistory").append(row);
      }
    }

    // Render All Crossings Log (Tab 4)
    if ($("crossingsLog")) {
      $("crossingsLog").replaceChildren();
      for (const item of data.crossings_log || []) {
        const row = document.createElement("tr");
        textCell(row, formatIST(item.observed_at));
        textCell(row, `${item.showroom || "-"} / ${item.camera_name || item.camera_id}`);
        const dirCell = textCell(row, "");
        const dirSpan = document.createElement("span");
        dirSpan.className = item.direction === "IN" ? "badge-in" : "badge-out";
        dirSpan.textContent = item.direction;
        dirCell.append(dirSpan);
        const catCell = textCell(row, "");
        const catBadge = document.createElement("span");
        if (item.category === "staff") {
          catBadge.className = "badge-tag badge-staff";
          catBadge.textContent = item.staff_name ? `STAFF (${item.staff_name})` : "STAFF";
        } else {
          catBadge.className = "badge-tag badge-visitor";
          catBadge.textContent = "VISITOR";
        }
        catCell.append(catBadge);
        $("crossingsLog").append(row);
      }
    }

    // Render Connection Logs
    $("history").replaceChildren();
    for (const log of data.report.connection_log) {
      const p = document.createElement("p");
      p.textContent =
        formatIST(log.at) +
        " · " +
        (data.cameras.find((c) => c.id === log.camera_id)?.name ||
          log.camera_id) +
        " · " +
        log.state;
      $("history").append(p);
    }
  } catch (e) {
    notify(e.message);
  } finally {
    refreshing = false;
  }
}
session().catch(() => {});
setInterval(refresh, 3000);

let selectedCamera = null,
  previewUrl = null,
  previewBusy = false;
$("closePreview").onclick = () => {
  selectedCamera = null;
  $("previewPanel").hidden = true;
};
setInterval(async () => {
  if (!csrf || !selectedCamera || previewBusy) return;
  previewBusy = true;
  const id = selectedCamera;
  try {
    const [imgRes, healthRes] = await Promise.all([
      fetch("/api/preview?id=" + encodeURIComponent(id)),
      fetch("/api/cameras/health?id=" + encodeURIComponent(id)),
    ]);
    if (id !== selectedCamera) return;
    if (imgRes.status === 200) {
      const url = URL.createObjectURL(await imgRes.blob());
      $("preview").src = url;
      $("preview").hidden = false;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = url;
      $("previewStatus").textContent = "Recent annotated frame";
    } else {
      $("preview").hidden = true;
      $("previewStatus").textContent =
        "No recent frame. Check camera connection.";
    }
    if (healthRes.ok) {
      const h = await healthRes.json();
      $("cameraHealthStats").textContent =
        `Stream Health: ${h.is_healthy ? "HEALTHY" : "DEGRADED"} | Dropped stale frames: ${h.frames_dropped_stale} (${h.drop_rate_pct}%) | Processed: ${h.frames_processed} | Reconnects: ${h.reconnect_count}`;
    }
  } catch {
    $("previewStatus").textContent = "Preview unavailable.";
  } finally {
    previewBusy = false;
  }
}, 1000);

let editingCamera = null;
$("lineForm").onsubmit = async (event) => {
  event.preventDefault();
  try {
    await api("/api/cameras/configure", {
      id: editingCamera,
      axis: $("lineAxis").value,
      position: Number($("linePosition").value) / 100,
      in_positive: $("lineDirection").value === "positive",
      zone_mode: $("lineZoneMode").checked,
    });
    $("linePanel").hidden = true;
    notify("Line & mode saved. Start the camera and check its preview.");
    await refresh();
  } catch (e) {
    notify(e.message);
  }
};
