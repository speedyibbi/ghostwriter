"""Minimal in-memory Supabase client for workflow unit tests."""

from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace
from typing import Any


class _Result:
    def __init__(self, data: list[dict] | None = None):
        self.data = data if data is not None else []


class _TableQuery:
    def __init__(self, store: InMemorySupabase, table: str):
        self._store = store
        self._table = table
        self._filters: list[tuple[str, Any]] = []
        self._neq: tuple[str, Any] | None = None
        self._order_col: str | None = None
        self._limit: int | None = None
        self._update_payload: dict | None = None
        self._insert_payload: dict | list[dict] | None = None

    def select(self, *_cols: str) -> _TableQuery:
        return self

    def eq(self, column: str, value: Any) -> _TableQuery:
        self._filters.append((column, value))
        return self

    def neq(self, column: str, value: Any) -> _TableQuery:
        self._neq = (column, value)
        return self

    def order(self, column: str, **_kwargs: Any) -> _TableQuery:
        self._order_col = column
        return self

    def limit(self, count: int) -> _TableQuery:
        self._limit = count
        return self

    def update(self, payload: dict) -> _TableQuery:
        self._update_payload = payload
        return self

    def insert(self, payload: dict | list[dict]) -> _TableQuery:
        self._insert_payload = payload
        return self

    def execute(self) -> _Result:
        if self._insert_payload is not None:
            return self._do_insert()
        if self._update_payload is not None:
            return self._do_update()
        return self._do_select()

    def _rows(self) -> list[dict]:
        if self._table == "books":
            return list(self._store.books.values())
        if self._table == "chapters":
            return list(self._store.chapters.values())
        return []

    def _matches(self, row: dict) -> bool:
        for column, value in self._filters:
            if row.get(column) != value:
                return False
        if self._neq:
            column, value = self._neq
            if row.get(column) == value:
                return False
        return True

    def _do_select(self) -> _Result:
        rows = [copy.deepcopy(r) for r in self._rows() if self._matches(r)]
        if self._order_col:
            rows.sort(key=lambda r: r.get(self._order_col) or 0)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)

    def _do_update(self) -> _Result:
        updated: list[dict] = []
        target = self._store.books if self._table == "books" else self._store.chapters
        for row_id, row in list(target.items()):
            if self._matches(row):
                row.update(self._update_payload or {})
                updated.append(copy.deepcopy(row))
        return _Result(updated)

    def _do_insert(self) -> _Result:
        target = self._store.books if self._table == "books" else self._store.chapters
        payloads = (
            self._insert_payload
            if isinstance(self._insert_payload, list)
            else [self._insert_payload]
        )
        inserted: list[dict] = []
        for payload in payloads:
            row = copy.deepcopy(payload)
            row.setdefault("id", str(uuid.uuid4()))
            target[row["id"]] = row
            inserted.append(copy.deepcopy(row))
        return _Result(inserted)


class InMemorySupabase:
    def __init__(self) -> None:
        self.books: dict[str, dict] = {}
        self.chapters: dict[str, dict] = {}

    def table(self, name: str) -> _TableQuery:
        return _TableQuery(self, name)

    def add_book(self, book_id: str, **fields: Any) -> dict:
        row = {
            "id": book_id,
            "title": "Test Book",
            "notes_before_outline": "Notes",
            "outline_status": "pending",
            "final_status": "pending",
            **fields,
        }
        self.books[book_id] = row
        return row

    def add_chapter(self, chapter_id: str, book_id: str, **fields: Any) -> dict:
        row = {
            "id": chapter_id,
            "book_id": book_id,
            "chapter_index": 1,
            "title": "Chapter One",
            "status": "pending",
            **fields,
        }
        self.chapters[chapter_id] = row
        return row

    def get_book(self, book_id: str) -> dict:
        return copy.deepcopy(self.books[book_id])

    def get_chapter(self, chapter_id: str) -> dict:
        return copy.deepcopy(self.chapters[chapter_id])


def result(data: list[dict] | None = None) -> SimpleNamespace:
    return SimpleNamespace(data=data or [])
