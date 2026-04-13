-- =============================================================================
-- Ghostwriter — initial schema
-- =============================================================================
-- This file is mounted at /docker-entrypoint-initdb.d and runs automatically
-- the first time the PostgreSQL container initialises (i.e. when the volume is
-- empty). Re-running it against an existing DB will error on duplicate objects;
-- bring the volume down first if you need a clean reset:
--   docker compose down -v && docker compose up -d
-- =============================================================================


-- ── PostgREST role ──
-- PostgREST uses SET LOCAL ROLE to switch to this role for every request that
-- carries the anon JWT. The postgres superuser must be able to assume it.

CREATE ROLE anon NOLOGIN;
GRANT anon TO postgres;
GRANT USAGE ON SCHEMA public TO anon;


-- ── Status enum ──
-- Using a CHECK constraint rather than a Postgres ENUM makes it easy to add
-- values later without a migration that requires an exclusive table lock.

CREATE DOMAIN workflow_status AS TEXT
    CHECK (VALUE IN (
        'pending',
        'in_review',
        'needs_revision',
        'approved',
        'error',
        'completed'
    ));


-- ── books ──

CREATE TABLE books (
    id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Import deduplication: set to the source row identifier (e.g. Excel row
    -- number or Sheet row ID) so the import script can skip already-imported rows.
    source_id            TEXT          UNIQUE,

    title                TEXT          NOT NULL,
    notes_before_outline TEXT          NOT NULL,

    -- Populated by the outline service after generation.
    outline              TEXT,
    -- Optional revision notes the editor submits after reviewing the outline.
    notes_after_outline  TEXT,
    -- Tracks where the outline stage is in the workflow.
    outline_status       workflow_status NOT NULL DEFAULT 'pending',

    -- Optional notes on the fully compiled draft.
    final_notes          TEXT,
    -- Tracks where the final compilation stage is.
    -- Set to 'in_review' once all chapters are approved.
    final_status         workflow_status NOT NULL DEFAULT 'pending',

    -- Local filesystem path written by the compilation service.
    output_path          TEXT,

    -- Last error message recorded when outline_status or final_status = 'error'.
    error_message        TEXT,

    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now()
);


-- ── chapters ──

CREATE TABLE chapters (
    id              UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id         UUID             NOT NULL REFERENCES books(id) ON DELETE CASCADE,

    -- 1-based position within the book, extracted from the outline.
    chapter_index   INTEGER          NOT NULL,
    title           TEXT,

    -- Populated by the chapter generation service.
    content         TEXT,
    -- LLM-generated summary injected as context into subsequent chapter prompts.
    summary         TEXT,

    -- Optional revision notes from the editor.
    notes           TEXT,
    status          workflow_status  NOT NULL DEFAULT 'pending',

    -- Incremented each time the chapter is regenerated, used to detect loops.
    revision_count  INTEGER          NOT NULL DEFAULT 0,

    -- Last error message when status = 'error'.
    error_message   TEXT,

    created_at      TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT now(),

    UNIQUE (book_id, chapter_index)
);

CREATE INDEX idx_chapters_book_id ON chapters (book_id);


-- ── logs ──

CREATE TABLE logs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id     UUID        REFERENCES books(id)    ON DELETE SET NULL,
    chapter_id  UUID        REFERENCES chapters(id) ON DELETE SET NULL,
    -- Short machine-readable event name, e.g. 'outline_generated', 'chapter_error'.
    event       TEXT        NOT NULL,
    message     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_logs_book_id    ON logs (book_id);
CREATE INDEX idx_logs_chapter_id ON logs (chapter_id);


-- ── updated_at trigger ──

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER books_set_updated_at
    BEFORE UPDATE ON books
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER chapters_set_updated_at
    BEFORE UPDATE ON chapters
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ── PostgREST grants ──
-- The anon role (used for all supabase-py requests) needs full CRUD access.
-- No Row-Level Security is configured; access is controlled at the application
-- layer (workflow runner + FastAPI routes).

GRANT SELECT, INSERT, UPDATE, DELETE ON books    TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON chapters TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON logs     TO anon;
