"""
rag.py — THE BACKEND, UNCHANGED.

Every line of RAG logic below is lifted verbatim from
langchain-rag-agent-youtube-video-summary-creator.ipynb. Cell numbers are
noted inline. Nothing about the retrieval, embedding, chunking, model, prompt,
or chain has been modified. This file is deliberately isolated so the pipeline
is provably identical to the notebook — the web layer (app.py) never touches it.
"""

# Imports — notebook cells 3 + 29
import os
import json
import tempfile
import subprocess
from http.cookiejar import MozillaCookieJar
from requests import Session
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import IpBlocked, RequestBlocked
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import (
    RunnableParallel,
    RunnablePassthrough,
    RunnableLambda,
)
from langchain_core.output_parsers import StrOutputParser


# ---------------------------------------------------------------------------
# Transcript fetching with automatic yt-dlp fallback on IP blocks
# ---------------------------------------------------------------------------

def _fetch_via_transcript_api(video_id: str) -> tuple[str, int]:
    """Primary method: youtube_transcript_api with browser-like session."""
    session = Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })

    cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(cookies_path):
        try:
            cj = MozillaCookieJar(cookies_path)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies.update(cj)
        except Exception as cookie_err:
            print(f"Warning: Failed to load cookies.txt: {cookie_err}")

    ytt_api = YouTubeTranscriptApi(http_client=session)
    transcript_list = ytt_api.list(video_id)

    # Find any English transcript (manually created or generated)
    transcript = None
    for t in transcript_list:
        if t.language_code.startswith("en"):
            transcript = t
            break

    # If no English transcript, try to translate any available one
    if not transcript:
        for t in transcript_list:
            if t.is_translatable:
                transcript = t.translate("en")
                break

    if not transcript:
        raise Exception(
            "No English or translatable transcript available for this video."
        )

    fetched = transcript.fetch()
    text = " ".join(chunk.text for chunk in fetched.snippets)
    return text, len(fetched.snippets)


def _fetch_via_ytdlp(video_id: str) -> tuple[str, int]:
    """Fallback method: use yt-dlp to download subtitles."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = os.path.join(tmpdir, "subs")
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-lang", "en",
            "--sub-format", "json3",
            "--extractor-args", "youtube:player_client=default,-tv,web_safari,web_embedded,-android_sdkless",
            "--output", out_template,
        ]
        
        # Pass cookies to yt-dlp if available
        cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        if os.path.exists(cookies_path):
            cmd.extend(["--cookies", cookies_path])
            
        cmd.append(url)
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=90
        )
        if result.returncode != 0:
            raise Exception(
                f"yt-dlp failed (exit {result.returncode}): {result.stderr.strip()}"
            )

        # yt-dlp writes files like subs.en.json3
        sub_file = None
        for fname in os.listdir(tmpdir):
            if fname.endswith(".json3"):
                sub_file = os.path.join(tmpdir, fname)
                break

        if not sub_file:
            raise Exception(
                "yt-dlp did not produce any English subtitle file for this video."
            )

        with open(sub_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        segments = []
        for event in data.get("events", []):
            segs = event.get("segs", [])
            for seg in segs:
                txt = seg.get("utf8", "").strip()
                if txt and txt != "\n":
                    segments.append(txt)

        if not segments:
            raise Exception("yt-dlp subtitle file was empty.")

        text = " ".join(segments)
        return text, len(segments)


def _fetch_transcript(video_id: str) -> tuple[str, int]:
    """Try youtube_transcript_api first; auto-fallback to yt-dlp on IP block."""
    try:
        return _fetch_via_transcript_api(video_id)
    except (IpBlocked, RequestBlocked) as ip_err:
        print(f"IP blocked by YouTube ({type(ip_err).__name__}). "
              f"Falling back to yt-dlp...")
        try:
            return _fetch_via_ytdlp(video_id)
        except Exception as fallback_err:
            raise Exception(
                f"Both transcript methods failed. "
                f"Primary: {ip_err} | Fallback (yt-dlp): {fallback_err}"
            )
    except Exception as e:
        raise Exception(f"YouTube Transcript Error: {str(e)}")


def build_rag(video_id: str):
    """Returns (retriever, main_chain, meta) for a given video id.

    This is the notebook's pipeline, in order, with the same parameters.
    """

    # Cell 7 — fetch transcript
    transcript, snippet_count = _fetch_transcript(video_id)

    # Cell 13 — chunk
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.create_documents([transcript])

    # Cell 16 — embed + index
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vector_store = FAISS.from_documents(chunks, embeddings)

    # Cell 19 — retriever
    retriever = vector_store.as_retriever(
        search_type="similarity", search_kwargs={"k": 5}
    )

    # Cell 22 — llm
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    # Cell 23 — grounding prompt (kept exactly, including whitespace)
    prompt = PromptTemplate(
        template="""
      You are a helpful assistant.
      Answer ONLY from the provided transcript context.
      If the context is insufficient, just say you don't know.

      {context}
      Question: {question}
    """,
        input_variables=["context", "question"],
    )

    # Cell 30 — format retrieved docs
    def format_docs(retrieved_docs):
        context_text = "\n\n".join(doc.page_content for doc in retrieved_docs)
        return context_text

    # Cells 31, 33, 34 — LCEL chain
    parallel_chain = RunnableParallel(
        {
            "context": retriever | RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
    )
    parser = StrOutputParser()
    main_chain = parallel_chain | prompt | llm | parser

    meta = {
        "video_id": video_id,
        "chunk_count": len(chunks),
        "snippet_count": snippet_count,
        "transcript_chars": len(transcript),
        "transcript_preview": transcript[:600],
    }
    return retriever, main_chain, meta
