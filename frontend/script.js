// AI Debate Arena — EventSource client + GSAP entrance animations.
// Spec 03 §4 reference shape, kept framework-free per AGENT.md §2.3.

const form = document.getElementById("topic-form");
const input = document.getElementById("topic-input");
const status = document.getElementById("status");
const transcript = document.getElementById("transcript");
const startBtn = document.getElementById("start-btn");

let currentSource = null; // track the open EventSource so we can close it on re-submit

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const topic = input.value.trim();
  if (!topic) return; // empty handled server-side too, but skip the round-trip

  // Reset UI for a fresh debate.
  transcript.innerHTML = "";
  status.classList.remove("hidden");
  startBtn.disabled = true;
  if (currentSource) currentSource.close();

  // Spec 03 §3: GET with topic as a query param. EventSource only supports GET.
  const url = `/debate?topic=${encodeURIComponent(topic)}`;
  const source = new EventSource(url);
  currentSource = source;

  source.onmessage = (event) => {
    const { speaker, text } = JSON.parse(event.data);
    appendTurn(speaker, text);
  };

  // Backend sends `event: done` when the stream is finished (backend/main.py).
  source.addEventListener("done", () => {
    source.close();
    currentSource = null;
    finishUi();
  });

  // Network drop, server restart (HF cold start), etc. EventSource auto-reconnects,
  // which would replay the whole debate — so close explicitly and show a message.
  source.onerror = () => {
    source.close();
    currentSource = null;
    finishUi();
    appendTurn("System", "Connection lost. Please try again.");
  };
});

function finishUi() {
  status.classList.add("hidden");
  startBtn.disabled = false;
}

function appendTurn(speaker, text) {
  const el = document.createElement("div");
  el.className = "turn";
  el.dataset.speaker = speaker;
  // textContent for the body avoids injecting any HTML/markdown the LLM emits; the
  // <strong> label is safe (fixed strings). CSS `white-space: pre-wrap` preserves
  // the verdict's line breaks.
  const label = document.createElement("strong");
  label.textContent = speaker;
  const body = document.createElement("p");
  body.textContent = text;
  el.appendChild(label);
  el.appendChild(body);
  transcript.appendChild(el);

  animateTurn(el, speaker);
}

// GSAP entrance animations, keyed per speaker (Spec 03 §2 hook-point notes):
// For slides from left, Against from right, Moderator fades+scales in.
function animateTurn(el, speaker) {
  if (!window.gsap) return; // graceful no-op if CDN blocked
  const base = { opacity: 0, duration: 0.5, ease: "power2.out" };
  if (speaker === "Debater For") {
    gsap.from(el, { ...base, x: -30 });
  } else if (speaker === "Debater Against") {
    gsap.from(el, { ...base, x: 30 });
  } else if (speaker.startsWith("Moderator")) {
    gsap.from(el, { ...base, scale: 0.96 });
  } else {
    gsap.from(el, { ...base, y: 10 });
  }
}
