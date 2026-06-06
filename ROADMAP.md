# Ghostwriter Roadmap

Living plan for what’s shipped, what’s next, and what’s deferred. Priorities are ordered by impact on day-to-day use and workflow reliability.

---

## Completed

| Item | Notes |
|------|-------|
| Outline revision notes in regeneration | `notes_after_outline` + previous outline injected into outline prompt |
| Background jobs + UI polling | Thread pool, `processing` status, HTTP 202, 2s poll in `book.html` |
| LLM response handling | `extract_text()` for blocked/empty/safety responses |
| Outline parse validation | Shared parser, post-generation check, UI chapter list + disabled approve |
| Workflow guard tests | 35 tests (`pytest`): parse, LLM extract, runner guards, API layer |
| Local security | `BIND_HOST=127.0.0.1`, optional `API_KEY` + `static/api.js` |

---

## P1 — Reliability & recovery

Fix “stuck book” and silent-failure scenarios. **Do these first.**

| # | Item | Problem | Direction |
|---|------|---------|-----------|
| 1.1 | Stuck `processing` recovery | Server crash mid-job leaves rows in `processing` with no retry | Add Cancel/Retry in UI; optional startup sweep or stale-job timeout → `error` |
| 1.2 | Summary retry + UI warning | Summary failures are logged but invisible; later chapters lose context | “Regenerate summary” action; warning badge on approved chapters with summary error |
| 1.3 | Dependency-aware `/health` | `/health` always returns ok | Check PostgREST/Postgres; optionally verify required env vars |
| 1.4 | Revision loop guardrails | `revision_count` tracked but not surfaced | Show count in UI; optional cap + alert on high counts |

**Suggested sprint:** 1.1 → 1.2 → 1.3 → 1.4

---

## P2 — Editor UX

Improve visibility and reduce friction for the human-in-the-loop workflow.

| # | Item | Problem | Direction |
|---|------|---------|-----------|
| 2.1 | Activity log in UI | `logs` table populated but never shown | Recent events panel on book page |
| 2.2 | Book list progress | Index only shows raw statuses | e.g. “3/8 chapters approved”, outline/final at a glance |
| 2.3 | Edit pre-outline notes in UI | Brief fixes require re-import or DB edit | Form on book page while `outline_status === pending'` |
| 2.4 | Download compiled output | Output path shown as text only | `GET /api/books/{id}/download` (zip of `.docx` + `.txt`) |
| 2.5 | Email deep links | Notifications are plain text | Include `http://localhost:8000/book/{id}` (or configurable base URL) |

---

## P3 — Output quality

Polish generated artifacts and prompt robustness.

| # | Item | Problem | Direction |
|---|------|---------|-----------|
| 3.1 | `.docx` paragraph splitting | Whole chapter is one paragraph | Split on blank lines (or light markdown) in `compilation.py` |
| 3.2 | Safer prompt templating | User notes with `{` break `.format()` | `string.Template`, Jinja2, or manual placeholder replace |
| 3.3 | Per-stage model config | Single `GEMINI_MODEL` for everything | e.g. `GEMINI_MODEL_CHAPTER`, `GEMINI_MODEL_SUMMARY` in settings |

---

## P4 — Platform & maintainability

Project hygiene and deployability.

| # | Item | Problem | Direction |
|---|------|---------|-----------|
| 4.1 | CI pipeline | No automated checks on push | GitHub Action: `ruff` + `pytest` |
| 4.2 | Pin dependencies | Loose `>=` in `requirements.txt` | Lock file or pinned versions |
| 4.3 | App containerization | Only Supabase is in Docker | Dockerfile + compose service for FastAPI |
| 4.4 | README / docs sync | Some tables still describe `needs_revision` flow | Align docs with `processing`-based workflow |
| 4.5 | Gemini SDK migration | `google.generativeai` deprecated | Migrate to `google.genai` |

---

## P5 — Future features

After the core workflow feels solid.

| # | Item | Notes |
|---|------|-------|
| 5.1 | Research augmentation | Implement optional `context` in chapter generation (search API or embeddings) |
| 5.2 | In-app import | Upload Excel or trigger import from UI instead of CLI-only |
| 5.3 | Final draft review loop | Wire `final_notes` + re-compile after compilation |
| 5.4 | Multi-editor / auth | If exposed beyond localhost: RLS, real auth, or nginx reverse proxy |

---

## Next up (recommended)

```
P1.1  Stuck processing recovery
P1.2  Summary retry + UI warning
P2.1  Activity log on book page
P2.4  Download endpoint
P3.1  Docx paragraph splitting
P4.1  CI (pytest + ruff)
```

---

## How to use this doc

- Pick the next item from **Next up** or the top of an open priority tier.
- When something ships, move it to **Completed** and note the PR or commit.
- Re-order within a tier if user feedback shifts (e.g. import UX before download).
