// AI Debate Arena — EventSource client + GSAP entrance animations.
// Spec 03 §4 reference shape, kept framework-free per AGENT.md §2.3.
//
// v1.3: two modes. "classic" = the original fixed-5-turn flow (one EventSource
// stream that ends with event:done). "open" = open-ended: turns stream, then the
// stream pauses (event:paused) and the user clicks Another round / Judge it now.

const form = document.getElementById("topic-form");
const input = document.getElementById("topic-input");
const status = document.getElementById("status");
const transcript = document.getElementById("transcript");
const startBtn = document.getElementById("start-btn");
const modelForSelect = document.getElementById("model-for");
const modelAgainstSelect = document.getElementById("model-against");
const advancedPanel = document.getElementById("advanced");
// v1.3 open-ended controls
const openControls = document.getElementById("open-controls");
const nextRoundBtn = document.getElementById("next-round-btn");
const judgeBtn = document.getElementById("judge-btn");
const stopBtn = document.getElementById("stop-btn");

let currentSource = null;       // open EventSource (classic or one open-ended round)
let openSessionId = null;       // session id for the active open-ended debate

// v1.1: populate the per-side model dropdowns from the deployer's provider.
populateModels();

async function populateModels() {
  try {
    const res = await fetch("/models");
    const { models } = await res.json();
    if (!Array.isArray(models) || models.length === 0) {
      advancedPanel.classList.add("hidden");
      return;
    }
    for (const id of models) {
      modelForSelect.add(new Option(id, id));
      modelAgainstSelect.add(new Option(id, id));
    }
    modelForSelect.disabled = false;
    modelAgainstSelect.disabled = false;
  } catch {
    advancedPanel.classList.add("hidden");
  }
}

function selectedMode() {
  const checked = document.querySelector('input[name="mode"]:checked');
  return checked ? checked.value : "open";
}

function resetUi() {
  transcript.innerHTML = "";
  status.classList.remove("hidden");
  startBtn.disabled = true;
  openControls.classList.add("hidden");
  if (currentSource) currentSource.close();
}

function finishUi() {
  status.classList.add("hidden");
  startBtn.disabled = false;
  openControls.classList.add("hidden");
}

// --- Shared turn rendering (used by BOTH modes) -------------------------------

function appendTurn(speaker, text) {
  const el = document.createElement("div");
  el.className = "turn";
  el.dataset.speaker = speaker;
  const label = document.createElement("strong");
  label.textContent = speaker;
  const body = document.createElement("p");
  body.textContent = text;
  el.appendChild(label);
  el.appendChild(body);
  transcript.appendChild(el);
  animateTurn(el, speaker);
}

function animateTurn(el, speaker) {
  if (!window.gsap) return;
  const base = { opacity: 0, duration: 0.5, ease: "power2.out" };
  if (speaker === "Debater For") gsap.from(el, { ...base, x: -30 });
  else if (speaker === "Debater Against") gsap.from(el, { ...base, x: 30 });
  else if (speaker.startsWith("Moderator")) gsap.from(el, { ...base, scale: 0.96 });
  else gsap.from(el, { ...base, y: 10 });
}

// --- Submit dispatcher --------------------------------------------------------

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const topic = input.value.trim();
  if (!topic) return;
  if (selectedMode() === "classic") startClassic(topic);
  else startOpen(topic);
});

// --- Classic mode (unchanged behavior: one stream, fixed 5 turns) -------------

function startClassic(topic) {
  resetUi();
  const params = new URLSearchParams({ topic });
  if (modelForSelect.value) params.set("model_for", modelForSelect.value);
  if (modelAgainstSelect.value) params.set("model_against", modelAgainstSelect.value);
  const source = new EventSource(`/debate?${params.toString()}`);
  currentSource = source;

  source.onmessage = (event) => {
    const { speaker, text } = JSON.parse(event.data);
    appendTurn(speaker, text);
  };
  source.addEventListener("done", () => {
    source.close();
    currentSource = null;
    finishUi();
  });
  source.onerror = () => {
    source.close();
    currentSource = null;
    finishUi();
    appendTurn("System", "Connection lost. Please try again.");
  };
}

// --- Open-ended mode (v1.3: user chooses when to judge) ----------------------

async function startOpen(topic) {
  resetUi();
  // 1. Create the session (POST because EventSource can't send a body).
  try {
    const body = { topic };
    if (modelForSelect.value) body.model_for = modelForSelect.value;
    if (modelAgainstSelect.value) body.model_against = modelAgainstSelect.value;
    const res = await fetch("/debate/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      finishUi();
      appendTurn("System", err.error || "Could not start the debate.");
      return;
    }
    const { session_id } = await res.json();
    openSessionId = session_id;
  } catch {
    finishUi();
    appendTurn("System", "Connection lost. Please try again.");
    return;
  }
  // 2. Open the initial stream (first For+Against round).
  openRound(`/debate/${openSessionId}/stream`);
}

function openRound(url) {
  // Each round is its own EventSource. The stream runs 2 turns then sends
  // event:paused and closes — we reopen on "Another round". Auto-verdict
  // (20-turn cap) sends event:verdict then event:done and we stop.
  if (currentSource) currentSource.close();
  const source = new EventSource(url);
  currentSource = source;

  source.addEventListener("turn", (event) => {
    const { speaker, text } = JSON.parse(event.data);
    appendTurn(speaker, text);
  });
  source.addEventListener("verdict", (event) => {
    const { speaker, text } = JSON.parse(event.data);
    appendTurn(speaker, text);
  });
  source.addEventListener("paused", () => {
    source.close();
    currentSource = null;
    // Round done, debate still live — show the controls so the user decides.
    status.classList.add("hidden");
    openControls.classList.remove("hidden");
  });
  source.addEventListener("done", () => {
    // Whole debate over (verdict delivered, either by user or auto-cap).
    source.close();
    currentSource = null;
    finishUi();
    openSessionId = null;
  });
  source.onerror = () => {
    source.close();
    currentSource = null;
    finishUi();
    appendTurn("System", "Connection lost. Please try again.");
    openSessionId = null;
  };
}

nextRoundBtn.addEventListener("click", () => {
  if (!openSessionId) return;
  status.classList.remove("hidden");
  openControls.classList.add("hidden");
  openRound(`/debate/${openSessionId}/next`);
});

judgeBtn.addEventListener("click", async () => {
  if (!openSessionId) return;
  if (currentSource) { currentSource.close(); currentSource = null; }
  openControls.classList.add("hidden");
  status.textContent = "Generating verdict…";
  status.classList.remove("hidden");
  try {
    const res = await fetch(`/debate/${openSessionId}/verdict`, { method: "POST" });
    const data = await res.json();
    appendTurn(data.speaker, data.text);
  } catch {
    appendTurn("System", "Could not generate the verdict. Please try again.");
  }
  status.textContent = "Debate in progress…"; // restore default text for next debate
  finishUi();
  openSessionId = null;
});

stopBtn.addEventListener("click", () => {
  if (openSessionId) {
    fetch(`/debate/${openSessionId}`, { method: "DELETE" }).catch(() => {});
  }
  if (currentSource) { currentSource.close(); currentSource = null; }
  openSessionId = null;
  finishUi();
});
