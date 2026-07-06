# Spec 04 — Deployment (Hugging Face Spaces, Docker SDK)

Since the backend is FastAPI (not the Gradio SDK template), this Space uses HF's
**Docker SDK** option instead. Slightly more setup than a Gradio Space, but still free
and still a single repo.

---

## 1. Space Configuration

- **SDK**: Docker (select this when creating the Space, not Gradio/Streamlit)
- **Hardware**: Free CPU basic tier
- **Visibility**: Public, unless there's a reason to keep it private during development
- **Port**: HF Spaces' Docker SDK expects the app to listen on port **7860** by default
  — confirm this in the Dockerfile and `uvicorn` command below

## 2. Required Files at Repo Root

```
Dockerfile
requirements.txt
README.md          # HF Spaces uses the YAML frontmatter for Space metadata
.gitignore
backend/            # FastAPI app
frontend/           # static HTML/CSS/JS served by FastAPI
```

`README.md` frontmatter for a Docker Space:

```yaml
---
title: AI Debate Arena
emoji: 🎤
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---
```

## 3. Dockerfile (Reference)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

EXPOSE 7860

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

## 4. FastAPI Static File Serving

`backend/main.py` must mount the `frontend/` directory so the browser can load
`index.html`, `style.css`, `script.js` alongside the `/debate` SSE endpoint:

```python
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
```

Mount this **after** defining the `/debate` route, so the SSE route isn't shadowed
by the static file catch-all.

## 5. requirements.txt (Starting Point — Pin Exact Versions at Build Time)

```
fastapi
uvicorn[standard]
crewai
python-dotenv
```

Pin exact versions once local dev is confirmed working, same reasoning as before —
floating versions risk "works locally, breaks on Space" build failures.

## 6. Secrets Handling

- Never commit `.env` or hardcode any API key
- The app is provider-agnostic (see AGENT.md §2 point 2 and Spec 01 §0). The deployer
  sets three HF Spaces repository secrets — same three as the local `.env`:
  - `OPENAI_API_BASE` — provider endpoint (documented default: `https://api.groq.com/openai/v1`)
  - `OPENAI_API_KEY` — key for that provider
  - `MODEL_NAME` — model id, no prefix (documented default: `llama-3.3-70b-versatile`)
- Code reads all three via `os.getenv(...)` — same local/prod code path
- To switch providers (e.g. Groq → OpenAI → Ollama), change these three secrets on HF
  Spaces; no code change or redeploy of the image logic is needed (HF will rebuild the
  same image with the new env values)

## 7. Cold Start Behavior

Same as before — free Spaces sleep after inactivity, first request after waking will
be slow. No in-memory state to worry about since v1 has none (AGENT.md §2 point 6).
Confirm during Phase 4 testing that:
- The Docker container rebuilds/restarts cleanly after a sleep cycle
- SSE connections aren't left in a broken state if the Space was mid-restart when a
  request came in — a dropped connection should just show the frontend's `onerror`
  message (Spec 03 §4), not hang indefinitely

## 8. Deployment Steps (Reference)

1. Create new Space on huggingface.co, SDK = Docker
2. Push via git remote (HF Spaces are git repos) — include `Dockerfile`, `requirements.txt`,
   `backend/`, `frontend/`, `README.md` with correct frontmatter
3. Add the three provider secrets (`OPENAI_API_BASE`, `OPENAI_API_KEY`, `MODEL_NAME`)
   as repository secrets before first run — see §6
4. Watch the build logs — Docker builds are more verbose than Gradio SDK builds,
   read errors carefully (most common: wrong port, missing dependency, path typo
   in `COPY`/`CMD`)
5. Once live, test the actual public URL end-to-end: load the page, submit a topic,
   confirm SSE streaming actually renders turns incrementally (not just "the API works
   via curl") — the browser-side EventSource behavior is what actually matters
6. Update PROGRESS.md Phase 4 checklist and note the live Space URL for future reference

## 9. Local Dev Note

Locally, run the backend directly instead of via Docker for faster iteration:

```bash
uvicorn backend.main:app --reload --port 7860
```

Only build/test the actual Docker image right before deploying, to catch any
environment differences (e.g. missing system deps) before they surface on HF's build.
