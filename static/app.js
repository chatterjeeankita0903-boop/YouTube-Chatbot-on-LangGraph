// TranscriptBooth — frontend logic. Talks to the Flask wrapper around the
// existing LangChain RAG chain (rag.py). No RAG logic here; rendering only.

const $ = (id) => document.getElementById(id);
const thread = $("thread");
const input = $("input");
const send = $("send");
const buildBtn = $("buildBtn");
const newvidBtn = $("newvidBtn");
const videoInput = $("videoInput");

let ready = false;

const STARTERS = [
  "Summarize the video",
  "What are the key takeaways?",
  "Who is mentioned and what did they say?",
  "What's the main argument?",
];

// ---------- helpers ----------
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3800);
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function clearEmpty() {
  const e = $("empty");
  if (e) e.remove();
}

function addMessage(role, text) {
  clearEmpty();
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  
  let content = escapeHtml(text);
  if (role === "bot" && typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
    content = DOMPurify.sanitize(marked.parse(text));
  }

  wrap.innerHTML = `
    <div class="who">${role === "user" ? "You" : "Booth"}</div>
    <div class="bubble markdown-body">${content}</div>`;
  thread.appendChild(wrap);
  thread.scrollTop = thread.scrollHeight;
  return wrap;
}

function addStarters() {
  const wrap = document.createElement("div");
  wrap.className = "starters";
  wrap.id = "starters";
  STARTERS.forEach((q) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = q;
    b.onclick = () => {
      input.value = q;
      ask();
    };
    wrap.appendChild(b);
  });
  thread.appendChild(wrap);
  thread.scrollTop = thread.scrollHeight;
}

function addTyping() {
  clearEmpty();
  const wrap = document.createElement("div");
  wrap.className = "msg bot typing";
  wrap.innerHTML = `<div class="who">Booth</div><div class="bubble"><i></i><i></i><i></i></div>`;
  thread.appendChild(wrap);
  thread.scrollTop = thread.scrollHeight;
  return wrap;
}

// signature element: render the actual passages the retriever returned
function addSources(sources) {
  if (!sources || !sources.length) return;
  const det = document.createElement("details");
  det.className = "sources";
  const items = sources
    .map(
      (s, i) =>
        `<div class="passage"><span class="pnum">${String(i + 1).padStart(2, "0")}</span>${escapeHtml(
          s.trim()
        )}</div>`
    )
    .join("");
  det.innerHTML = `
    <summary><span class="chev">▸</span>Grounded in ${sources.length} passage${
    sources.length > 1 ? "s" : ""
  }</summary>
    <div class="passages">${items}</div>`;
  thread.appendChild(det);
  thread.scrollTop = thread.scrollHeight;
}

function setPipelineStep(name, status) {
  const el = document.querySelector(`.step[data-step="${name}"]`);
  if (!el) return;
  el.classList.remove("active", "done");
  if (status) el.classList.add(status);
  if (status === "done") el.querySelector(".tick").textContent = "✓";
  if (status === "active") el.querySelector(".tick").textContent = "▸";
}

function setLive(on, label) {
  const onair = $("onair");
  onair.className = on ? "onair live" : "onair";
  onair.querySelector(".dot").nextSibling.textContent = label;
}

// ---------- build knowledge base ----------
async function build() {
  const video = videoInput.value.trim();
  if (!video) return toast("Paste a YouTube link or video id.");

  buildBtn.disabled = true;
  buildBtn.textContent = "Building…";
  setLive(false, "loading");
  $("pipeline").classList.add("show");
  ["fetch", "chunk", "embed", "index"].forEach((s) => setPipelineStep(s, null));
  setPipelineStep("fetch", "active");

  try {
    const res = await fetch("/api/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Couldn't build the knowledge base.");

    $("chunkN").textContent = data.meta.chunk_count;
    ["fetch", "chunk", "embed", "index"].forEach((s) => setPipelineStep(s, "done"));

    setLive(true, "on air");
    $("videoState").textContent = `${data.meta.video_id} · ${data.meta.chunk_count} passages indexed`;

    const thumb = $("thumb");
    thumb.href = `https://www.youtube.com/watch?v=${data.meta.video_id}`;
    $("thumbImg").src = `https://img.youtube.com/vi/${data.meta.video_id}/hqdefault.jpg`;
    thumb.classList.add("show");
    newvidBtn.classList.add("show");

    ready = true;
    input.disabled = false;
    send.disabled = false;
    input.placeholder = "Ask anything about this video…";
    thread.innerHTML = "";
    addMessage("bot", "Knowledge base ready. Ask me anything — I'll answer only from this video's transcript.");
    addStarters();
    input.focus();
  } catch (e) {
    setPipelineStep("fetch", null);
    setLive(false, "off air");
    toast(e.message);
  } finally {
    buildBtn.disabled = false;
    buildBtn.textContent = "Build knowledge base";
  }
}

// ---------- ask ----------
async function ask() {
  const q = input.value.trim();
  if (!q || !ready) return;
  const starters = $("starters");
  if (starters) starters.remove();

  addMessage("user", q);
  input.value = "";
  input.style.height = "auto";
  input.disabled = true;
  send.disabled = true;
  const typing = addTyping();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();
    typing.remove();
    if (!data.ok) throw new Error(data.error || "Something went wrong.");
    addMessage("bot", data.answer);
    addSources(data.sources);
  } catch (e) {
    typing.remove();
    addMessage("bot", "I hit a snag answering that. " + e.message);
  } finally {
    input.disabled = false;
    send.disabled = false;
    input.focus();
  }
}

// ---------- reset / new video ----------
async function newVideo() {
  try {
    await fetch("/api/reset", { method: "POST" });
  } catch (e) {
    /* non-fatal */
  }
  ready = false;
  input.disabled = true;
  send.disabled = true;
  input.placeholder = "Build a knowledge base first…";
  $("pipeline").classList.remove("show");
  $("thumb").classList.remove("show");
  newvidBtn.classList.remove("show");
  $("videoState").textContent = "";
  setLive(false, "off air");
  videoInput.value = "";
  thread.innerHTML = `
    <div class="empty" id="empty">
      <div class="eyebrow">Grounded · No hallucinations</div>
      <h1>Put a video on the record.</h1>
      <p>Paste a YouTube link and I'll answer only from what's actually said in it — with the source passages to prove it.</p>
    </div>`;
  videoInput.focus();
}

// ---------- events ----------
buildBtn.addEventListener("click", build);
newvidBtn.addEventListener("click", newVideo);
videoInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") build();
});
send.addEventListener("click", ask);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    ask();
  }
});
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
});
