"""Record what people search for and what JEV creates.

By default everything goes to the console as JSON lines (Railway keeps these
in its log viewer). Start with capture on (`--capture` or JEV_CAPTURE=1) and a
DATABASE_URL to store it in Postgres instead.
"""

import atexit
import json
import logging
import os
import queue
import sys
import threading
import time

log = logging.getLogger("interjev.record")

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    visitor_id  text,
    query       text NOT NULL,
    results     jsonb,
    cached      boolean NOT NULL DEFAULT false,
    model       text,
    duration_ms integer,
    error       text
);
CREATE INDEX IF NOT EXISTS searches_created_at_idx ON searches (created_at);

CREATE TABLE IF NOT EXISTS pages (
    id          bigserial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    visitor_id  text,
    url         text NOT NULL,
    host        text,
    method      text,
    form        jsonb,
    referrer    text,
    title       text,
    html        text,
    model       text,
    duration_ms integer,
    error       text
);
CREATE INDEX IF NOT EXISTS pages_created_at_idx ON pages (created_at);
CREATE INDEX IF NOT EXISTS pages_host_idx ON pages (host);
"""

COLUMNS = {
    "searches": ("visitor_id", "query", "results", "cached", "model", "duration_ms", "error"),
    "pages": ("visitor_id", "url", "host", "method", "form", "referrer", "title", "html", "model",
              "duration_ms", "error"),
}
JSON_COLUMNS = {"results", "form"}


class ConsoleRecorder:
    """Log every event as a single JSON line on stdout."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self._lock = threading.Lock()

    def record(self, table: str, **fields) -> None:
        line = json.dumps({"event": {"searches": "search", "pages": "page"}.get(table, table), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields},
                          ensure_ascii=False, default=str)
        with self._lock:
            print("[interjev]", line, file=self.stream, flush=True)

    def close(self) -> None:
        pass


class PostgresRecorder:
    """Write events to Postgres from a background thread.

    Requests never wait on the database, and a database outage only costs the
    events (they fall back to the console) rather than breaking the app.
    """

    def __init__(self, dsn: str, fallback: ConsoleRecorder | None = None):
        import psycopg  # only needed when capture is on

        self._psycopg = psycopg
        self.dsn = dsn
        self.fallback = fallback or ConsoleRecorder()
        self._queue: queue.Queue = queue.Queue(maxsize=10_000)
        self._conn = None
        self._connect()  # fail fast on a bad DATABASE_URL at startup
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA)
        self._thread = threading.Thread(target=self._run, name="interjev-recorder", daemon=True)
        self._thread.start()

    def _connect(self):
        self._conn = self._psycopg.connect(self.dsn, autocommit=True, connect_timeout=10)

    def record(self, table: str, **fields) -> None:
        try:
            self._queue.put_nowait((table, fields))
        except queue.Full:
            self.fallback.record(table, **fields)

    def _insert(self, table: str, fields: dict) -> None:
        from psycopg.types.json import Jsonb

        cols = [c for c in COLUMNS[table] if c in fields]
        values = [Jsonb(fields[c]) if c in JSON_COLUMNS and fields[c] is not None else fields[c] for c in cols]
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        with self._conn.cursor() as cur:
            cur.execute(sql, values)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            table, fields = item
            for attempt in (1, 2):
                try:
                    if self._conn is None or self._conn.closed:
                        self._connect()
                    self._insert(table, fields)
                    break
                except Exception as exc:  # reconnect once, then give up on this event
                    self._conn = None
                    if attempt == 2:
                        log.warning("Postgres write failed (%s); logging to console instead", exc)
                        self.fallback.record(table, **fields)
            self._queue.task_done()

    def flush(self, timeout: float = 5) -> None:
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.02)

    def close(self) -> None:
        self.flush()
        self._queue.put(None)


def capture_enabled() -> bool:
    return os.environ.get("JEV_CAPTURE", "").lower() in ("1", "true", "yes", "on")


def make_recorder():
    if not capture_enabled():
        return ConsoleRecorder()
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("Capture is on (JEV_CAPTURE / --capture) but DATABASE_URL is not set")
    recorder = PostgresRecorder(dsn)
    atexit.register(recorder.close)  # flush queued events on shutdown
    log.warning("interJEV capture on: recording searches and pages to Postgres")
    return recorder
