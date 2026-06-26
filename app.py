"""
app.py — the web layer.

Responsibilities (NONE of which touch RAG logic — that lives in rag.py):
  - serve the chat UI
  - give each browser its own session so multiple people / videos don't collide
  - read the OpenAI key from the environment (instead of kaggle_secrets)
  - turn a pasted YouTube URL into the 11-char id the notebook expects
  - expose /api/build, /api/ask, /api/reset, /api/health
"""

import os
import re
import uuid
from collections import OrderedDict
from threading import Lock

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

import rag  # the untouched notebook pipeline

load_dotenv()
if not os.environ.get("OPENAI_API_KEY"):
    print("WARNING: OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", os.urandom(24).hex())

# ----------------------------------------------------------------------------
# Per-session store. Each browser session owns its own retriever + chain so the
# app is genuinely multi-user. Capped + LRU-evicted so memory can't grow forever
# (each FAISS index is held in RAM).
# ----------------------------------------------------------------------------
MAX_SESSIONS = 25
_sessions = OrderedDict()  # sid -> {"retriever", "main_chain", "meta"}
_lock = Lock()


def _sid() -> str:
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


def _store(sid, payload):
    with _lock:
        _sessions[sid] = payload
        _sessions.move_to_end(sid)
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)


def _get(sid):
    with _lock:
        if sid in _sessions:
            _sessions.move_to_end(sid)
            return _sessions[sid]
    return None


def extract_video_id(value: str) -> str:
    """Pull the 11-char id from a YouTube URL, or pass a bare id through."""
    value = (value or "").strip()
    for pattern in (
        r"(?:v=|/shorts/|/embed/|youtu\.be/)([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$",
    ):
        m = re.search(pattern, value)
        if m:
            return m.group(1)
    return value


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "has_key": bool(os.environ.get("OPENAI_API_KEY")),
                    "active_sessions": len(_sessions)})


@app.route("/api/build", methods=["POST"])
def api_build():
    sid = _sid()
    video_id = extract_video_id((request.get_json(force=True) or {}).get("video", ""))
    if not video_id:
        return jsonify({"ok": False, "error": "Paste a YouTube link or video id."}), 400

    try:
        retriever, main_chain, meta = rag.build_rag(video_id)
        _store(sid, {"retriever": retriever, "main_chain": main_chain, "meta": meta})
        return jsonify({"ok": True, "meta": meta})
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = str(e)
        msg_lower = msg.lower()
        if "fallback (yt-dlp):" in msg_lower:
            # If yt-dlp failed, extract its specific error to show to the user
            fallback_err = msg.split("Fallback (yt-dlp):")[1].strip()
            msg = f"Railway IP is blocked, and the yt-dlp fallback also failed: {fallback_err}"
        elif "ipblocked" in msg_lower or "requestblocked" in msg_lower or "blocking requests from your ip" in msg_lower:
            msg = "YouTube is blocking requests from this server (IP Blocked). You may need to configure a proxy or try a different network."
        elif "videounavailable" in msg_lower or "video is unavailable" in msg_lower:
            msg = "This YouTube video is unavailable or private. Please check the video URL."
        elif "transcriptsdisabled" in msg_lower or "transcripts are disabled" in msg_lower:
            msg = "Subtitles/transcripts are disabled for this video. Please try a video with captions enabled."
        elif "notranscriptfound" in msg_lower or "no english" in msg_lower:
            msg = "This video has no English or translatable transcript available."
        elif "transcript" in msg_lower or "subtitle" in msg_lower:
            msg = "This video has no fetchable English transcript. Try one with captions enabled."
        return jsonify({"ok": False, "error": msg}), 400


@app.route("/api/ask", methods=["POST"])
def api_ask():
    state = _get(_sid())
    if not state:
        return jsonify({"ok": False, "error": "Build a video knowledge base first."}), 400

    question = ((request.get_json(force=True) or {}).get("question") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "Ask a question."}), 400

    try:
        # answer — notebook cell 35
        answer = state["main_chain"].invoke(question)
        # the exact passages the retriever returned, for the sources panel
        docs = state["retriever"].invoke(question)
        sources = [d.page_content for d in docs]
        return jsonify({"ok": True, "answer": answer, "sources": sources})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/reset", methods=["POST"])
def api_reset():
    sid = _sid()
    with _lock:
        _sessions.pop(sid, None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
