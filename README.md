# TranscriptBooth

A full-stack chatbot over the existing LangChain RAG notebook
(`langchain-rag-agent-youtube-video-summary-creator.ipynb`). Paste a YouTube
link, build a knowledge base, and ask questions answered **only** from that
video's transcript — every answer shows the exact passages it was grounded in.

## Architecture

```
 Browser (HTML/CSS/JS)
    │  fetch JSON
    ▼
 Flask  app.py ── sessions, routes, URL→id helper, key from env
    │  calls
    ▼
 rag.py ── YOUR NOTEBOOK PIPELINE, UNCHANGED
           transcript → chunk(1000/200) → embed(text-embedding-3-small)
           → FAISS → retriever(similarity, k=5) → gpt-4o-mini(temp 0.2)
           → grounding prompt → parallel_chain | prompt | llm | parser
```

The RAG layer is isolated in `rag.py` so it's provably identical to the
notebook. `app.py` never modifies it — it only serves the UI and routes
requests. Each browser session gets its own in-memory vector store + chain
(LRU-capped), so multiple people/videos don't collide.

## Run locally

### On Windows (Recommended)
Simply run the PowerShell script to automate setup, dependency installation, `.env` file creation, and server launch:
```powershell
./run.ps1
```

### On macOS / Linux
Run the shell script:
```bash
./run.sh
```

### Manual Setup (All Platforms)
```bash
# Create and activate virtual environment
python -m venv venv
# On macOS/Linux:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
# On macOS/Linux:
cp .env.example .env
# On Windows:
copy .env.example .env

# Open .env and paste your OpenAI key, then launch the server
python app.py               # → http://localhost:5000
```

## Run with Docker

```bash
docker build -t transcriptbooth .
docker run -p 5000:5000 --env-file .env transcriptbooth
```

## API

| Method | Route          | Body                  | Returns                          |
|--------|----------------|-----------------------|----------------------------------|
| GET    | `/`            | —                     | chat UI                          |
| GET    | `/api/health`  | —                     | `{ok, has_key, active_sessions}` |
| POST   | `/api/build`   | `{video}`             | `{ok, meta}` (chunk count, id…)  |
| POST   | `/api/ask`     | `{question}`          | `{ok, answer, sources[]}`        |
| POST   | `/api/reset`   | —                     | `{ok}`                           |

## What changed vs. the notebook

Nothing in the RAG pipeline. Web glue only: a Flask server, sessions, key from
`OPENAI_API_KEY` instead of `kaggle_secrets`, and a URL→video-id helper.

## Notes

- Single gunicorn worker by design — the FAISS indexes live in process memory.
  For horizontal scaling, move the vector store to a shared/persistent backend
  (Chroma/Pinecone) and the sessions to Redis.
- Streaming token output and timestamped passages are natural next steps; the
  retriever already carries the data for the latter.

## Files

```
app.py                 Flask web layer (sessions, routes)
rag.py                 the untouched notebook pipeline
templates/index.html   chat UI markup
static/styles.css      visual system
static/app.js          build / ask / reset, source rendering
Dockerfile, run.sh     deployment
```
