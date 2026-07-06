# Spec 03 — Frontend (Plain HTML/CSS/JS + GSAP)

No framework. No build step. Three static files served directly by FastAPI
(`backend/main.py` mounts `frontend/` as static files). GSAP and any UI/UX styling
skill are applied by the developer's own code-assistant tooling on top of the structure
defined here — this spec defines the HTML hook points and data contract, not the final
visual design.

---

## 1. File Structure

```
frontend/
├── index.html
├── style.css
└── script.js
```

## 2. HTML Structure (Reference Skeleton)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AI Debate Arena</title>
  <link rel="stylesheet" href="style.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
</head>
<body>
  <main id="app">
    <h1>🎤 AI Debate Arena</h1>

    <form id="topic-form">
      <input type="text" id="topic-input" placeholder="e.g. Is remote work better than office work?" required>
      <button type="submit" id="start-btn">Start Debate</button>
    </form>

    <div id="status" class="hidden">Debate in progress...</div>

    <div id="transcript"></div>
  </main>

  <script src="script.js"></script>
</body>
</html>
```

**Hook points for GSAP / UI-UX skill to target** (do not rename these IDs without
updating `script.js` accordingly):
- `#topic-form` — entrance animation on page load
- `#start-btn` — click/press feedback animation
- `#status` — fade in/out when debate starts/ends
- `#transcript` — container that turn elements get appended into
- Each appended turn element gets class `.turn` and a data attribute
  `data-speaker="Debater For|Debater Against|Moderator — Final Verdict"` so GSAP
  can target different entrance animations per speaker (e.g. slide from left for
  For, slide from right for Against, fade+scale for Moderator).

## 3. Backend Contract (What script.js Talks To)

Single endpoint, GET request with topic as a query param, response is SSE:

```
GET /debate?topic=<url-encoded topic>
```

Each event's `data:` payload is JSON: `{"speaker": "...", "text": "..."}`
Stream ends with `event: done`.

## 4. script.js (Reference Implementation Shape)

```javascript
const form = document.getElementById("topic-form");
const input = document.getElementById("topic-input");
const status = document.getElementById("status");
const transcript = document.getElementById("transcript");
const startBtn = document.getElementById("start-btn");

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const topic = input.value.trim();
  if (!topic) return;

  transcript.innerHTML = "";
  status.classList.remove("hidden");
  startBtn.disabled = true;

  const source = new EventSource(`/debate?topic=${encodeURIComponent(topic)}`);

  source.onmessage = (event) => {
    const { speaker, text } = JSON.parse(event.data);
    appendTurn(speaker, text);
  };

  source.addEventListener("done", () => {
    source.close();
    status.classList.add("hidden");
    startBtn.disabled = false;
  });

  source.onerror = () => {
    source.close();
    status.classList.add("hidden");
    startBtn.disabled = false;
    appendTurn("System", "Connection lost. Please try again.");
  };
});

function appendTurn(speaker, text) {
  const el = document.createElement("div");
  el.className = "turn";
  el.dataset.speaker = speaker;
  el.innerHTML = `<strong>${speaker}:</strong><p>${text}</p>`;
  transcript.appendChild(el);

  // GSAP entrance animation hook — implementing agent wires actual animation here,
  // e.g.: gsap.from(el, { opacity: 0, y: 20, duration: 0.5 });
  if (window.gsap) {
    gsap.from(el, { opacity: 0, y: 20, duration: 0.5 });
  }
}
```

Note: `EventSource` only supports GET requests natively, which is why the topic is
passed as a query param rather than a POST body. Do not switch to `fetch()` +
manual stream parsing unless there's a concrete reason — `EventSource` is simpler
and handles reconnection semantics for free.

## 5. Explicitly Out of Scope for v1

- No CSS framework (Tailwind, Bootstrap) — plain CSS or whatever the UI/UX skill
  generates, kept dependency-free per AGENT.md's no-build-step constraint
- No dark/light theme toggle
- No mobile-specific breakpoints beyond basic responsive CSS
- No client-side routing — this is a single static page
