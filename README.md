# Ghostwriter — Automated Book Generation System

An end-to-end, modular AI-powered system for generating structured books using LLMs with human-in-the-loop (HITL) feedback, state-driven workflows, and persistent context management.

Designed to run **locally**. The only external dependency is the Gemini API for LLM calls.

---

## Overview

This project implements a pipeline that:

1. Accepts a **book title + editorial notes** (imported from Excel or Google Sheets)
2. Generates a structured **outline** via Gemini
3. Iteratively generates **chapters with contextual memory** (summaries of prior chapters)
4. Supports **human feedback loops** at the outline and chapter stages via a local web UI
5. Compiles the final approved draft into exportable formats

The system is designed to be:

- **Modular** — each stage is an independent service; the workflow runner composes them
- **State-driven** — all progression is controlled by status fields in Supabase
- **Resumable** — safe to stop and restart; state is always in the DB
- **UI-triggered** — editor actions in the web UI advance the workflow; no external webhooks needed
- **Extensible** — research augmentation can be added later without changing the core interface

---

## System Architecture

```
Import Script (Excel / Google Sheets)
↓
[books row created in Supabase]
↓
Web UI: Editor adds pre-outline notes → submits
↓
Outline Generator (Gemini)
↓
Web UI: Editor reviews outline → approves or submits revision notes
↓
Chapter Generator Loop (Gemini + cumulative summaries)
  ↓ per chapter:
  Web UI: Editor reviews chapter → approves or submits revision notes
↓
Final Compilation (.docx / .txt)
↓
Output saved locally + SMTP notification sent
```

The **workflow runner** (`app/workflow/runner.py`) is the central state machine. It reads a book's current status from Supabase and dispatches to the appropriate service. All other components are stateless.

---

## Tech Stack

| Component         | Technology                                      |
|-------------------|-------------------------------------------------|
| Backend           | Python + FastAPI                                |
| Frontend          | Vanilla HTML / CSS / JS (served by FastAPI)     |
| Database          | Supabase (PostgreSQL)                           |
| LLM               | Gemini (`google-generativeai` SDK)              |
| Input Import      | `openpyxl` (Excel) / `gspread` (Google Sheets) |
| Output Formats    | `python-docx` (`.docx`), plain write (`.txt`)  |
| Notifications     | SMTP via Python `smtplib` (stdlib)              |
| Prompt Management | Plain `.txt` template files with `.format()`   |

---

## Project Structure

```
ghostwriter/
├── main.py                      # FastAPI app entry point
├── requirements.txt
├── .env.example
│
├── app/
│   ├── core/
│   │   ├── config.py            # Env vars and settings (pydantic-settings)
│   │   └── database.py          # Supabase client singleton
│   │
│   ├── llm/
│   │   ├── client.py            # Thin Gemini wrapper: retry, error handling, .generate()
│   │   └── prompts/
│   │       ├── outline.txt      # Prompt template for outline generation
│   │       ├── chapter.txt      # Prompt template for chapter generation
│   │       └── summary.txt      # Prompt template for chapter summarization
│   │
│   ├── services/
│   │   ├── outline.py           # Outline generation logic
│   │   ├── chapter.py           # Chapter generation + summarization
│   │   ├── compilation.py       # Assemble final .docx / .txt from approved chapters
│   │   └── notification.py      # SMTP email triggers
│   │
│   ├── workflow/
│   │   └── runner.py            # State machine: reads DB status → dispatches to services
│   │
│   └── api/
│       ├── books.py             # Book CRUD + data endpoints for the UI
│       ├── chapters.py          # Chapter data endpoints for the UI
│       └── workflow.py          # POST endpoints that trigger workflow steps (UI → backend)
│
├── static/                      # Web UI (served by FastAPI as static files)
│   ├── index.html               # Book list view + import trigger
│   ├── book.html                # Per-book view: outline, chapters, notes forms
│   └── style.css
│
└── scripts/
    └── import_books.py          # One-time import from Excel / Google Sheets into Supabase
```

---

## Data Model (Supabase)

### Status Enum

A consistent set of status values used across both `books` and `chapters`:

| Value            | Meaning                                              |
|------------------|------------------------------------------------------|
| `pending`        | Not yet processed                                    |
| `in_review`      | Generated and waiting for editor action              |
| `needs_revision` | Editor submitted notes; regeneration required        |
| `approved`       | Editor approved; workflow may proceed                |
| `error`          | A failure occurred; see `error_message`              |
| `completed`      | Final state; no further action needed                |

---

### `books` Table

| Field                  | Type      | Description                                          |
|------------------------|-----------|------------------------------------------------------|
| `id`                   | uuid      | Primary key                                          |
| `source_id`            | text      | Row identifier from import source (deduplication)    |
| `title`                | text      | Book title                                           |
| `notes_before_outline` | text      | Mandatory pre-generation editorial notes             |
| `outline`              | text      | Generated outline (populated by workflow)            |
| `notes_after_outline`  | text      | Optional revision notes submitted after outline      |
| `outline_status`       | text      | Status enum value for the outline stage              |
| `final_notes`          | text      | Optional notes on the final compiled draft           |
| `final_status`         | text      | Status enum value for the final compilation stage    |
| `output_path`          | text      | Local filesystem path to the compiled output file    |
| `error_message`        | text      | Last error message if `outline_status = error`       |
| `created_at`           | timestamp | Auto-set on insert                                   |
| `updated_at`           | timestamp | Updated on every status change                       |

---

### `chapters` Table

| Field                 | Type      | Description                                          |
|-----------------------|-----------|------------------------------------------------------|
| `id`                  | uuid      | Primary key                                          |
| `book_id`             | uuid      | Foreign key → `books.id`                             |
| `chapter_index`       | integer   | 1-based order of the chapter                         |
| `title`               | text      | Chapter title (extracted from outline)               |
| `content`             | text      | Generated chapter text                               |
| `summary`             | text      | LLM-generated summary used as context for later chapters |
| `notes`               | text      | Optional revision notes from editor                  |
| `status`              | text      | Status enum value for this chapter                   |
| `revision_count`      | integer   | Number of times this chapter has been regenerated    |
| `error_message`       | text      | Last error message if `status = error`               |
| `created_at`          | timestamp | Auto-set on insert                                   |
| `updated_at`          | timestamp | Updated on every status change                       |

---

### `logs` Table

| Field        | Type      | Description                          |
|--------------|-----------|--------------------------------------|
| `id`         | uuid      | Primary key                          |
| `book_id`    | uuid      | Reference to the book (nullable)     |
| `chapter_id` | uuid      | Reference to the chapter (nullable)  |
| `event`      | text      | Event name (e.g. `outline_generated`)|
| `message`    | text      | Human-readable detail                |
| `created_at` | timestamp | Auto-set on insert                   |

---

## Workflow Stages

### Stage 1 — Import

Run once before starting the workflow:

```bash
python scripts/import_books.py
```

Reads rows from an Excel file or Google Sheet and inserts them into the `books` table. Uses `source_id` to prevent duplicate imports. Sets `outline_status = pending` on each new row.

---

### Stage 2 — Outline Generation

**Trigger:** Editor opens the book in the UI and clicks "Generate Outline".

**Requirements:** `title` and `notes_before_outline` must be present.

**Logic:**
1. Workflow runner calls the outline service with `title` + `notes_before_outline`
2. Gemini generates the outline using `prompts/outline.txt`
3. Outline stored in DB; `outline_status` set to `in_review`
4. SMTP notification sent to editor

**State transitions:**

| Editor action              | `outline_status` set to | Next step                    |
|----------------------------|--------------------------|------------------------------|
| Submits revision notes     | `needs_revision`         | Re-run outline generation    |
| Approves                   | `approved`               | Proceed to chapter generation|

---

### Stage 3 — Chapter Generation

**Trigger:** `outline_status = approved` → editor clicks "Start Chapters" in the UI.

**Key principle:** Each chapter is generated with cumulative summaries of all prior chapters injected into the prompt, maintaining coherence without passing full chapter text (token-efficient).

**Process (per chapter, sequential):**
1. Aggregate `summary` fields of all previously approved chapters
2. Call Gemini with `prompts/chapter.txt` (outline + summaries + chapter title)
3. Store `content` in DB; `status = in_review`
4. Call Gemini with `prompts/summary.txt` to generate and store `summary`
5. SMTP notification sent to editor

**State transitions (per chapter):**

| Editor action              | `status` set to  | Next step                    |
|----------------------------|------------------|------------------------------|
| Submits revision notes     | `needs_revision` | Re-run chapter generation    |
| Approves                   | `approved`       | Generate next chapter        |

When all chapters are `approved`, `books.final_status` is set to `in_review`.

---

### Stage 4 — Final Compilation

**Trigger:** All chapters approved → editor reviews in the UI and clicks "Compile".

**Logic:**
1. Assemble all chapters (ordered by `chapter_index`) into a single document
2. Output to `.docx` and/or `.txt` on the local filesystem
3. Store path in `books.output_path`
4. Set `books.final_status = completed`
5. Send SMTP notification with output path

---

## Context Handling Strategy

Instead of passing full chapter text (which is token-heavy), the system passes **cumulative summaries**:

```
You are writing Chapter 4 of a book titled "X".

Here is the full outline:
{outline}

Here is a summary of all chapters written so far:
{summaries}

Now write Chapter 4: "{chapter_title}".
```

Summaries are generated immediately after each chapter is approved and stored in the `chapters.summary` field.

---

## LLM Client Design

All LLM calls go through `app/llm/client.py`, which exposes a single interface:

```python
def generate(prompt: str) -> str
```

Internally this handles:
- Gemini API authentication
- Retry with exponential backoff on rate limit / transient errors
- Raising a structured exception on unrecoverable failure

Prompts are loaded from `.txt` files in `app/llm/prompts/` and populated using Python's `.format()`. This keeps prompt text editable without touching Python code.

---

## Research Augmentation (Future)

Not in scope for v1. The chapter service accepts an optional `context: str` parameter reserved for injected research content. To add research augmentation later, populate this parameter — no other interface changes are required.

Options when the time comes:
- **API-based search** — SerpAPI / Brave / Bing; summarize and inject
- **BYOD** — embeddings in a vector DB; retrieve relevant chunks per chapter
- **Native LLM search** — use a Gemini model with grounding/browsing enabled

---

## Input File Format

The import script expects a file (Excel or Google Sheet) with one row per book to generate. Only two columns are required:

| Column                 | Description                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| `title`                | The book title                                                              |
| `notes_before_outline` | Editorial brief: tone, audience, chapter count, style, any other guidance  |

Example:

| title                         | notes_before_outline                                                              |
|-------------------------------|-----------------------------------------------------------------------------------|
| The Art of War (Modern Edition) | Business audience. Keep chapters concise. Use modern corporate examples.        |
| Deep Work Summary             | Academic tone. 8 chapters. Include actionable takeaways at the end of each.       |

The sheet is **read-only input** — nothing is written back to it. All generated content lives in Supabase. The `source_id` column (auto-derived from the row identifier) prevents the same row from being imported twice.

---

## Docker Setup (Supabase)

Supabase runs locally via Docker Compose. The app itself runs directly on the host — only Supabase is containerized for now.

A `docker-compose.yml` at the project root brings up the full Supabase stack (PostgreSQL, PostgREST, GoTrue, Studio). After the containers are up, retrieve the local `SUPABASE_URL` and `SUPABASE_KEY` (anon key) from Supabase Studio at `http://localhost:54323`.

> Note: The app is structured to be Docker-friendly for a future full containerization. Keep all config in `.env`, avoid hardcoded host paths, and use `OUTPUT_DIR` for all file writes.

---

## Running the Project

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd ghostwriter
pip install -r requirements.txt
```

Use whatever Python toolchain you prefer (`pyenv`, `uv`, `venv`, `conda`, etc.). Python 3.11+ recommended.

### 2. Start Supabase

```bash
docker compose up -d
```

Wait for all services to be healthy, then open Supabase Studio at `http://localhost:54323` to confirm the DB is running and grab your local API credentials.

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

```
SUPABASE_URL=http://localhost:54321
SUPABASE_KEY=<anon key from Supabase Studio>
GEMINI_API_KEY=
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
SMTP_TO=
OUTPUT_DIR=./output

# Only required if importing from Google Sheets
GOOGLE_SHEETS_CREDENTIALS_JSON=
```

### 4. Import books

Prepare your input file (see [Input File Format](#input-file-format) above), then run:

```bash
# From an Excel file
python scripts/import_books.py --source books.xlsx

# From a Google Sheet (requires GOOGLE_SHEETS_CREDENTIALS_JSON in .env)
python scripts/import_books.py --source "https://docs.google.com/spreadsheets/d/<id>"
```

### 5. Start the server

```bash
python main.py
```

Open `http://localhost:8000` in your browser.
