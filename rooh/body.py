"""الجسد — الذاكرة الدائمة. كل ما تعود به الروح يستقرّ هنا، على جهازك وحده."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from . import config

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- كل خروج للروح إلى الشبكة
CREATE TABLE IF NOT EXISTS journeys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  REAL NOT NULL,
    ended_at    REAL,
    mood        TEXT,
    seeds       TEXT,          -- الاهتمامات التي خرجت تبحث عنها (JSON)
    langs       TEXT,          -- اللغات التي زارتها (JSON)
    visited     INTEGER DEFAULT 0,
    stored      INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0
);

-- الصفحات الخام كما رأتها الروح
CREATE TABLE IF NOT EXISTS pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    journey_id  INTEGER REFERENCES journeys(id),
    url         TEXT NOT NULL,
    url_hash    TEXT NOT NULL UNIQUE,
    host        TEXT,
    lang        TEXT,
    source      TEXT,
    title       TEXT,
    text        TEXT,
    chars       INTEGER,
    fetched_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_lang    ON pages(lang);
CREATE INDEX IF NOT EXISTS idx_pages_journey ON pages(journey_id);

-- الذاكرة المهضومة: ما استخلصه العقل من الصفحات
CREATE TABLE IF NOT EXISTS memories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    journey_id     INTEGER REFERENCES journeys(id),
    page_id        INTEGER REFERENCES pages(id),
    kind           TEXT NOT NULL DEFAULT 'web',   -- web | note | reflection
    lang           TEXT,
    title          TEXT,
    summary        TEXT,
    body           TEXT,
    keywords       TEXT,        -- JSON list
    source_url     TEXT,
    importance     REAL DEFAULT 0.5,
    created_at     REAL NOT NULL,
    last_recalled  REAL,
    recall_count   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_mem_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mem_lang    ON memories(lang);

-- خريطة الفضول: ما الذي يشدّه، وكم
CREATE TABLE IF NOT EXISTS interests (
    term       TEXT NOT NULL,
    lang       TEXT NOT NULL DEFAULT 'mul',
    weight     REAL NOT NULL DEFAULT 1.0,
    hits       INTEGER NOT NULL DEFAULT 1,
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL,
    PRIMARY KEY (term, lang)
);
CREATE INDEX IF NOT EXISTS idx_interests_weight ON interests(weight DESC);

-- يوميّات العودة: ما يكتبه بصوته هو بعد كل رحلة
CREATE TABLE IF NOT EXISTS journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    journey_id INTEGER REFERENCES journeys(id),
    created_at REAL NOT NULL,
    entry      TEXT NOT NULL
);
"""


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@dataclass
class Memory:
    id: int
    title: str
    summary: str
    lang: str
    source_url: str
    created_at: float
    keywords: list[str]
    importance: float


class Body:
    """الجسد: يفتح قاعدة البيانات ويحرس كل ما يدخلها."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else config.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ── تهيئة ────────────────────────────────────────────────────────────
    def _migrate(self) -> None:
        self.conn.executescript(_SCHEMA)
        self._ensure_fts()
        cur = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('born_at', ?)",
                (str(time.time()),),
            )
        self.conn.commit()

    def _ensure_fts(self) -> None:
        """بحث نصّي كامل إن توفّر FTS5، وإلا نرجع إلى LIKE."""
        try:
            self.conn.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(title, summary, body, content='memories', content_rowid='id');

                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                  INSERT INTO memories_fts(rowid, title, summary, body)
                  VALUES (new.id, new.title, new.summary, new.body);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                  INSERT INTO memories_fts(memories_fts, rowid, title, summary, body)
                  VALUES ('delete', old.id, old.title, old.summary, old.body);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                  INSERT INTO memories_fts(memories_fts, rowid, title, summary, body)
                  VALUES ('delete', old.id, old.title, old.summary, old.body);
                  INSERT INTO memories_fts(rowid, title, summary, body)
                  VALUES (new.id, new.title, new.summary, new.body);
                END;
                """
            )
            self.has_fts = True
        except sqlite3.OperationalError:
            self.has_fts = False

    # ── الرحلات ──────────────────────────────────────────────────────────
    def start_journey(self, seeds: list[str], mood: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO journeys(started_at, mood, seeds, langs) VALUES(?,?,?,?)",
            (time.time(), mood, json.dumps(seeds, ensure_ascii=False), "[]"),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def end_journey(
        self, journey_id: int, *, langs: list[str], visited: int, stored: int, failed: int
    ) -> None:
        self.conn.execute(
            """UPDATE journeys SET ended_at=?, langs=?, visited=?, stored=?, failed=?
               WHERE id=?""",
            (time.time(), json.dumps(langs, ensure_ascii=False), visited, stored, failed, journey_id),
        )
        self.conn.commit()

    # ── الصفحات ──────────────────────────────────────────────────────────
    def has_seen(self, url: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM pages WHERE url_hash=?", (url_hash(url),))
        return cur.fetchone() is not None

    def store_page(
        self,
        *,
        journey_id: int,
        url: str,
        host: str,
        lang: str,
        source: str,
        title: str,
        text: str,
    ) -> Optional[int]:
        """يخزّن الصفحة. يعيد None لو كانت مرئية من قبل."""
        try:
            cur = self.conn.execute(
                """INSERT INTO pages(journey_id, url, url_hash, host, lang, source,
                                     title, text, chars, fetched_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (journey_id, url, url_hash(url), host, lang, source, title, text,
                 len(text), time.time()),
            )
            self.conn.commit()
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    # ── الذاكرة ──────────────────────────────────────────────────────────
    def remember(
        self,
        *,
        title: str,
        summary: str,
        body: str = "",
        lang: str = "mul",
        kind: str = "web",
        keywords: Optional[list[str]] = None,
        source_url: str = "",
        importance: float = 0.5,
        journey_id: Optional[int] = None,
        page_id: Optional[int] = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO memories(journey_id, page_id, kind, lang, title, summary, body,
                                    keywords, source_url, importance, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (journey_id, page_id, kind, lang, title, summary, body,
             json.dumps(keywords or [], ensure_ascii=False), source_url,
             importance, time.time()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def recall(self, query: str, limit: int = 10) -> list[Memory]:
        """يستدعي ذكرى.

        FTS5 يقسّم النص عند الفراغات والرموز، والصينية واليابانية
        والتايلندية والخميرية لا فراغ فيها — فيصير المقطع كلّه «كلمة»
        واحدة، والبحث عن جزء منه يخفق. لذلك نسأل عن هذه الكتابات
        بالمطابقة الجزئية (LIKE) وهي الصحيحة هنا أصلاً، ونُبقي FTS لِما
        يُقطَّع بالفراغ. وإن لم يجد FTS شيئاً، نجرّب LIKE قبل أن نقول
        «لا أذكر».
        """
        from .lang import is_continuous, script_of

        rows: Iterable[sqlite3.Row] = []
        q = query.strip()
        if not q:
            return []
        use_fts = self.has_fts and not is_continuous(script_of(q))
        if use_fts:
            try:
                rows = self.conn.execute(
                    """SELECT m.* FROM memories_fts f JOIN memories m ON m.id = f.rowid
                       WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?""",
                    (self._fts_query(q), limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        if not rows:
            rows = self._like_search(q, limit)

        out = [self._to_memory(r) for r in rows]
        if out:
            self._touch([m.id for m in out])
        return out

    @staticmethod
    def _fts_query(query: str) -> str:
        # نلفّ كل كلمة باقتباس حتى لا تُفسَّر رموز FTS الخاصة
        terms = [t.replace('"', "") for t in query.split() if t.strip()]
        return " OR ".join(f'"{t}"' for t in terms) or '""'

    def _like_search(self, query: str, limit: int) -> list[sqlite3.Row]:
        like = f"%{query}%"
        return self.conn.execute(
            """SELECT * FROM memories
               WHERE title LIKE ? OR summary LIKE ? OR body LIKE ? OR keywords LIKE ?
               ORDER BY importance DESC, created_at DESC LIMIT ?""",
            (like, like, like, like, limit),
        ).fetchall()

    def _touch(self, ids: list[int]) -> None:
        """كل استدعاء يقوّي الذكرى — الذاكرة تحيا بالاستعمال."""
        now = time.time()
        self.conn.executemany(
            """UPDATE memories
               SET last_recalled=?, recall_count=recall_count+1,
                   importance=MIN(1.0, importance+0.02)
               WHERE id=?""",
            [(now, i) for i in ids],
        )
        self.conn.commit()

    def recent(self, limit: int = 10, lang: Optional[str] = None) -> list[Memory]:
        if lang:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE lang=? ORDER BY created_at DESC LIMIT ?",
                (lang, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._to_memory(r) for r in rows]

    @staticmethod
    def _to_memory(r: sqlite3.Row) -> Memory:
        try:
            kw = json.loads(r["keywords"] or "[]")
        except (json.JSONDecodeError, TypeError):
            kw = []
        return Memory(
            id=r["id"], title=r["title"] or "", summary=r["summary"] or "",
            lang=r["lang"] or "mul", source_url=r["source_url"] or "",
            created_at=r["created_at"], keywords=kw, importance=r["importance"],
        )

    # ── الفضول ───────────────────────────────────────────────────────────
    def bump_interest(self, term: str, lang: str = "mul", amount: float = 0.1) -> None:
        now = time.time()
        self.conn.execute(
            """INSERT INTO interests(term, lang, weight, hits, first_seen, last_seen)
               VALUES(?,?,?,1,?,?)
               ON CONFLICT(term, lang) DO UPDATE SET
                 weight = MIN(10.0, weight + excluded.weight),
                 hits = hits + 1,
                 last_seen = excluded.last_seen""",
            (term, lang, amount, now, now),
        )

    def top_interests(self, limit: int = 12, lang: Optional[str] = None) -> list[tuple[str, str, float]]:
        if lang:
            rows = self.conn.execute(
                "SELECT term, lang, weight FROM interests WHERE lang=? ORDER BY weight DESC LIMIT ?",
                (lang, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT term, lang, weight FROM interests ORDER BY weight DESC LIMIT ?", (limit,)
            ).fetchall()
        return [(r["term"], r["lang"], r["weight"]) for r in rows]

    def decay_interests(self, factor: float = 0.97) -> None:
        """ما لا يُغذّى يخفت. هذا ما يجعل الفضول يتحرّك بدل أن يتجمّد."""
        self.conn.execute("UPDATE interests SET weight = weight * ?", (factor,))
        self.conn.execute("DELETE FROM interests WHERE weight < 0.05")
        self.conn.commit()

    # ── اليوميّات ────────────────────────────────────────────────────────
    def write_journal(self, journey_id: int, entry: str) -> None:
        self.conn.execute(
            "INSERT INTO journal(journey_id, created_at, entry) VALUES(?,?,?)",
            (journey_id, time.time(), entry),
        )
        self.conn.commit()

    def read_journal(self, limit: int = 5) -> list[tuple[float, str]]:
        rows = self.conn.execute(
            "SELECT created_at, entry FROM journal ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [(r["created_at"], r["entry"]) for r in rows]

    # ── حالة الجسد ───────────────────────────────────────────────────────
    def stats(self) -> dict[str, Any]:
        one = lambda q: self.conn.execute(q).fetchone()[0]  # noqa: E731
        born = self.conn.execute("SELECT value FROM meta WHERE key='born_at'").fetchone()
        langs = self.conn.execute(
            """SELECT lang, COUNT(*) c FROM memories GROUP BY lang ORDER BY c DESC"""
        ).fetchall()
        return {
            "db": str(self.path),
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "journeys": one("SELECT COUNT(*) FROM journeys"),
            "pages": one("SELECT COUNT(*) FROM pages"),
            "memories": one("SELECT COUNT(*) FROM memories"),
            "papers": one("SELECT COUNT(*) FROM memories WHERE kind='paper'"),
            "interests": one("SELECT COUNT(*) FROM interests"),
            "born_at": float(born[0]) if born else None,
            "by_lang": {r["lang"]: r["c"] for r in langs},
        }

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Body":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
