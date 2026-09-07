const $ = (id) => document.getElementById(id);
let active = null,
  templateConfirmed = "",
  uploadId = "",
  pollTimer;
const stages = [
  ["research", "资料与学习目标"],
  ["script", "口播与内容审查"],
  ["slides", "生成或适配课件"],
  ["visual_review", "课件版式检查"],
  ["voice", "参考声音"],
  ["production", "配音、字幕与成片"],
  ["speech_review", "转写与漏读复核"],
  ["delivery", "检查与交付"],
];
const statusNames = {
  queued: "等待制作",
  running: "制作中",
  completed: "制作完成",
  failed: "需要处理",
  cancelled: "已取消",
  interrupted: "服务已中断",
};
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "X-Studio-Client": "1",
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let d;
    try {
      d = await response.json();
    } catch {}
    throw Error(
      typeof d?.detail === "string"
        ? d.detail
        : JSON.stringify(d?.detail || "请求失败"),
    );
  }
  return response.json();
}
function config() {
  return {
    kind: $("provider").value,
    model: $("model").value.trim(),
    base_url: $("baseUrl").value.trim(),
    api_key: $("apiKey").value,
    vision: $("vision").checked,
    json_mode: $("jsonMode").value,
  };
}
function savePrefs() {
  const c = config();
  delete c.api_key;
  localStorage.setItem("kvs-provider", JSON.stringify(c));
}
function providerUI() {
  const external = $("provider").value === "external";
  $("externalFields").hidden = !external;
  $("codexHint").hidden = external;
}
try {
  const c = JSON.parse(localStorage.getItem("kvs-provider") || "{}");
  for (const [key, id] of Object.entries({
    kind: "provider",
    model: "model",
    base_url: "baseUrl",
    json_mode: "jsonMode",
  }))
    if (c[key]) $(id).value = c[key];
  $("vision").checked = !!c.vision;
} catch {}
providerUI();
$("provider").onchange = providerUI;
$("modelToggle").onclick = () => {
  $("settings").hidden = !$("settings").hidden;
};
function showCreate() {
  active = null;
  $("creation").hidden = false;
  $("taskPanel").hidden = true;
  $("toast").hidden = true;
  window.scrollTo({ top: 0 });
}
$("newTask").onclick = showCreate;
$("backCreate").onclick = showCreate;
$("voiceFile").onchange = () => {
  uploadId = "";
  $("voiceName").textContent = $("voiceFile").files[0]?.name || "选择参考录音";
};
function mode() {
  return document.querySelector("[name=slidesMode]:checked").value;
}
function resetTemplate() {
  templateConfirmed = "";
  $("templatePreview").hidden = true;
  $("templateStatus").textContent =
    mode() === "generate" && !$("slidesPath").value
      ? "已选择内置教学模板"
      : "请检查并预览选定的 HTML";
  $("pathLabel").firstChild.textContent =
    mode() === "existing"
      ? "已有 HTML slides 的本地路径"
      : "参考模板 HTML 路径（可选）";
  $("slidesPath").placeholder =
    mode() === "existing"
      ? "/absolute/path/slides.html"
      : "留空使用内置黑底教学模板";
}
document
  .querySelectorAll("[name=slidesMode]")
  .forEach((x) => (x.onchange = resetTemplate));
$("slidesPath").oninput = resetTemplate;
$("inspect").onclick = async () => {
  try {
    $("toast").hidden = true;
    const path = $("slidesPath").value.trim();
    if (!path && mode() === "generate") {
      templateConfirmed = "default";
      $("templateStatus").textContent = "已确认内置黑底教学模板";
      $("templatePreview").hidden = false;
      $("templatePreview").querySelector("iframe").src =
        "/api/template/default";
      return;
    }
    const data = await api("/api/slides/inspect", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    templateConfirmed = path;
    $("templateStatus").textContent = `已确认 · ${data.slides.length} 页`;
    $("templatePreview").hidden = false;
    $("templatePreview").querySelector("iframe").src = data.preview;
  } catch (e) {
    toast(e.message);
  }
};
$("createForm").onsubmit = async (event) => {
  event.preventDefault();
  $("toast").hidden = true;
  $("start").disabled = true;
  try {
    const path = $("slidesPath").value.trim();
    if ((path || mode() === "existing") && templateConfirmed !== path)
      throw Error("请先检查并预览选定的课件");
    const file = $("voiceFile").files[0];
    if (file && !uploadId) {
      const form = new FormData();
      form.append("file", file);
      uploadId = (await api("/api/upload", { method: "POST", body: form })).id;
    }
    const request = {
      topic: $("topic").value.trim(),
      audience: $("audience").value,
      minutes: Number($("minutes").value),
      playback_speed: Number($("speed").value),
      provider: config(),
      voice_url: $("voiceUrl").value.trim(),
      profile_id: $("profileId").value.trim(),
      voice_path: $("voicePath").value.trim(),
      voice_upload: uploadId,
      reference_text: $("referenceText").value.trim(),
      slides_mode: mode(),
      slides_path: mode() === "existing" ? path : "",
      template_path: mode() === "generate" ? path : "",
      source_notes: $("sourceNotes").value.trim(),
      reference_urls: $("sourceUrls")
        .value.split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      chrome: $("chrome").value.trim(),
      subtitle_font: $("font").value.trim(),
    };
    savePrefs();
    const job = await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify(request),
    });
    await openJob(job.id);
    await refreshJobs();
  } catch (e) {
    toast(e.message);
  } finally {
    $("start").disabled = false;
  }
};
async function openJob(id) {
  active = id;
  $("creation").hidden = true;
  $("taskPanel").hidden = false;
  $("toast").hidden = true;
  renderTask(await api("/api/jobs/" + id));
  window.scrollTo({ top: 0 });
}
function renderTask(job) {
  if (job.id !== active) return;
  $("taskTitle").textContent = job.topic;
  $("taskStatus").textContent = statusNames[job.status] || job.status;
  const index =
    job.status === "completed"
      ? stages.length
      : Math.max(
          0,
          stages.findIndex((s) => s[0] === job.stage),
        );
  $("progressFill").style.width = (index / stages.length) * 100 + "%";
  $("taskMessage").textContent = job.message;
  $("steps").replaceChildren(
    ...stages.map(([id, title], i) => {
      const li = document.createElement("li");
      li.className = i < index ? "done" : i === index ? "current" : "";
      li.textContent =
        (i < index ? "✓ " : String(i + 1).padStart(2, "0") + "  ") + title;
      return li;
    }),
  );
  $("cancel").hidden = !["queued", "running"].includes(job.status);
  $("resume").hidden = !["failed", "cancelled", "interrupted"].includes(
    job.status,
  );
  $("logs").textContent = job.events
    .map((e) => new Date(e.time * 1000).toLocaleTimeString() + "  " + e.text)
    .join("\n");
  $("taskDuration").textContent = "";
  $("result").hidden = job.status !== "completed";
  if (job.status === "completed") {
    const base = "/artifacts/" + job.id + "/";
    const video = $("resultVideo");
    if (video.dataset.job !== job.id) {
      video.src = base + "build/video.mp4";
      video.dataset.job = job.id;
      $("chapters").replaceChildren(
        ...job.result.chapters.map((c) => {
          const b = document.createElement("button");
          b.textContent = fmt(c.time) + " " + c.title;
          b.onclick = () => {
            video.currentTime = c.time;
          };
          return b;
        }),
      );
    }
    for (const [id, path] of Object.entries({
      downloadVideo: "build/video.mp4",
      downloadSrt: "build/subtitles.srt",
      downloadScript: "script.md",
      downloadDesc: "description.md",
    })) {
      $(id).href = base + path;
      $(id).download = path.split("/").pop();
    }
    $("taskDuration").textContent = fmt(job.result.duration) + " · 1080p";
  }
}
function fmt(seconds) {
  return (
    String(Math.floor(seconds / 60)).padStart(2, "0") +
    ":" +
    String(Math.floor(seconds % 60)).padStart(2, "0")
  );
}
async function refreshJobs() {
  const jobs = await api("/api/jobs");
  $("jobs").replaceChildren(
    ...jobs.map((j) => {
      const b = document.createElement("button");
      b.className = "job";
      const title = document.createElement("strong");
      title.textContent = j.topic;
      const status = document.createElement("small");
      status.textContent = statusNames[j.status] || j.status;
      b.append(title, status);
      b.onclick = () => openJob(j.id).catch((e) => toast(e.message));
      return b;
    }),
  );
}
$("cancel").onclick = async () => {
  try {
    await api("/api/jobs/" + active + "/cancel", {
      method: "POST",
      body: "{}",
    });
  } catch (e) {
    toast(e.message);
  }
};
$("resume").onclick = async () => {
  try {
    await api("/api/jobs/" + active + "/resume", {
      method: "POST",
      body: JSON.stringify({ api_key: $("apiKey").value }),
    });
  } catch (e) {
    toast(e.message);
  }
};
async function boot() {
  try {
    const env = await api("/api/system");
    const ready =
      env.ffmpeg && env.node && env.media_installed && env.voice.loaded;
    $("health").textContent = ready ? "本地服务已就绪" : "环境需要配置";
    $("healthDot").style.background = ready ? "#16a34a" : "#d97706";
    $("health").title = JSON.stringify(env, null, 2);
    await refreshJobs();
  } catch (e) {
    toast(e.message);
  }
  pollTimer = setInterval(async () => {
    try {
      if (active) renderTask(await api("/api/jobs/" + active));
      await refreshJobs();
    } catch {}
  }, 2500);
}
boot();
