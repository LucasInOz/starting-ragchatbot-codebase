# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A full-stack Retrieval-Augmented Generation (RAG) system that answers questions about course materials. FastAPI backend, vanilla JS frontend, ChromaDB for vector storage, and Anthropic Claude (Sonnet 4) as the reasoning layer with tool-based retrieval.

## Commands

**Always use `uv` to manage dependencies and run code — never use `pip` directly.** Requires **Python 3.13+**.

```bash
# Install / sync dependencies (from project root)
uv sync

# Add or remove a dependency (edits pyproject.toml + uv.lock)
uv add <package>
uv remove <package>

# Run the app (from project root) — starts server on port 8000 with auto-reload
./run.sh
# ...or manually:
cd backend && uv run uvicorn app:app --reload --port 8000

# Run an arbitrary script/command in the project environment
uv run <command>

# Run a Python file — always via uv, never `python foo.py` directly
uv run python <file.py>
```

There is **no test suite, linter, or build step** configured in this repo.

A `.env` file at the project root with `ANTHROPIC_API_KEY=...` is **required** — `config.py` reads it via `python-dotenv` and Claude calls fail without it.

- Web UI: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs

## Architecture

The request flow that matters most (`frontend/script.js` → `backend/app.py` → `rag_system.py` → `ai_generator.py` → `search_tools.py` → `vector_store.py`):

1. **`app.py`** — FastAPI entry point. `POST /api/query` and `GET /api/courses`. Mounts the frontend as static files and, on startup, ingests `../docs` into ChromaDB. Mints a session ID if the request has none.
2. **`rag_system.py`** — Orchestrator. Owns one instance each of the document processor, vector store, AI generator, session manager, and tool manager. `query()` wires history + tools into the AI call, then reads sources back out of the tool manager.
3. **`ai_generator.py`** — Claude integration and the **tool-use loop**. This is the key control flow: Claude is called with `tool_choice: "auto"`; if it returns `stop_reason == "tool_use"`, the tool is executed and Claude is called a **second time (without tools)** to synthesize the final answer. The loop is **single-round** — one tool execution pass per query, reinforced by the system prompt's "one search per query maximum."
4. **`search_tools.py`** — `CourseSearchTool` (the `search_course_content` tool Claude sees) and `ToolManager`. The tool definition's schema is what Claude uses to decide whether/how to search.
5. **`vector_store.py`** — ChromaDB wrapper with **two collections**: `course_catalog` (course metadata, used for fuzzy course-name resolution) and `course_content` (the embedded text chunks that actually get searched). Search resolves a course name → builds a `where` filter → runs semantic query.

### Cross-cutting design notes

- **Tool-based (agentic) retrieval, not fixed RAG.** Claude decides *whether* to search. General-knowledge questions get answered with no search; only course-specific questions trigger the tool.
- **Sources flow through mutable state, not return values.** `CourseSearchTool` writes results to `self.last_sources`; `RAGSystem.query()` reads them back via `tool_manager.get_last_sources()` after the AI call, then `reset_sources()`. This works because it's single-threaded per request but is fragile under concurrency and only surfaces one search's sources.
- **Course title is the primary key.** `Course.title` is used as the ChromaDB document ID in `course_catalog`. Ingestion (`add_course_folder`) skips any course whose title already exists, so re-runs are idempotent. To force a re-index, delete `backend/chroma_db/`.
- **Two ingestion code paths chunk differently.** In `document_processor.py`, the per-lesson loop only prefixes the *first* chunk with lesson context, while the final-lesson block prefixes *every* chunk with course+lesson context. This inconsistency is real, not intentional.
- **PDF/DOCX are accepted by extension but not actually parsed.** `read_file` does plain UTF-8 text reads only; binary formats come through garbled despite the `.pdf/.docx` filter in `add_course_folder`.

### Configuration

All tunables live in `backend/config.py` (`Config` dataclass): model ID, embedding model (`all-MiniLM-L6-v2`), `CHUNK_SIZE` (800), `CHUNK_OVERLAP` (100), `MAX_RESULTS` (5), `MAX_HISTORY` (2 exchanges), and `CHROMA_PATH`.

### Expected course document format

Documents in `docs/` follow this structure (parsed by `document_processor.py`):

```
Course Title: [title]
Course Link: [url]
Course Instructor: [name]

Lesson 0: [lesson title]
Lesson Link: [url]
[lesson content...]

Lesson 1: [lesson title]
[lesson content...]
```
