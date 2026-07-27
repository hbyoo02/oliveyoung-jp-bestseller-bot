import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS rankings (
    date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    brand TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT,
    PRIMARY KEY (date, rank)
);

CREATE TABLE IF NOT EXISTS promotions (
    promo_name TEXT PRIMARY KEY,
    start_date TEXT NOT NULL,
    end_date TEXT,
    last_seen_date TEXT NOT NULL,
    url TEXT
);

CREATE TABLE IF NOT EXISTS promotion_products (
    promo_name TEXT NOT NULL,
    brand TEXT NOT NULL,
    product_name TEXT NOT NULL,
    PRIMARY KEY (promo_name, brand, product_name),
    FOREIGN KEY (promo_name) REFERENCES promotions(promo_name)
);

CREATE TABLE IF NOT EXISTS comments (
    date TEXT PRIMARY KEY,
    comment_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    slack_sent INTEGER DEFAULT 0
);
"""


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_rankings(db_path: str, date: str, items: list[dict]) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM rankings WHERE date = ?", (date,))
        conn.executemany(
            "INSERT INTO rankings (date, rank, brand, product_name, category) "
            "VALUES (:rank_date, :rank, :brand, :product_name, :category)",
            [
                {
                    "rank_date": date,
                    "rank": item["rank"],
                    "brand": item["brand"],
                    "product_name": item["product_name"],
                    "category": item.get("category"),
                }
                for item in items
            ],
        )


def get_rankings(db_path: str, date: str) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT rank, brand, product_name, category FROM rankings "
            "WHERE date = ? ORDER BY rank", (date,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_available_dates(db_path: str, before_or_on: str | None = None, limit: int = 30) -> list[str]:
    with _connect(db_path) as conn:
        if before_or_on:
            rows = conn.execute(
                "SELECT DISTINCT date FROM rankings WHERE date <= ? "
                "ORDER BY date DESC LIMIT ?", (before_or_on, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT date FROM rankings ORDER BY date DESC LIMIT ?", (limit,)
            ).fetchall()
        return [r["date"] for r in rows]


def get_latest_date_before(db_path: str, date: str) -> str | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM rankings WHERE date < ?", (date,)
        ).fetchone()
        return row["d"] if row and row["d"] else None


def upsert_promotion_seen(db_path: str, promo_name: str, today: str, url: str | None) -> None:
    """오늘 홈페이지 배너에서 발견된 기획전을 기록한다.

    처음 보는 기획전이면 start_date=today 로 새로 생성하고, 이미 있던 기획전이면
    (재개된 경우 포함) last_seen_date 만 갱신하고 end_date 는 다시 NULL 로 되돌린다.
    """
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO promotions (promo_name, start_date, end_date, last_seen_date, url) "
            "VALUES (?, ?, NULL, ?, ?) "
            "ON CONFLICT(promo_name) DO UPDATE SET "
            "last_seen_date=excluded.last_seen_date, end_date=NULL, url=excluded.url",
            (promo_name, today, today, url),
        )


def close_missing_promotions(db_path: str, seen_promo_names: set[str], today: str) -> None:
    """오늘 배너 목록에 더 이상 보이지 않는 기획전을 마지막으로 확인된 날짜로 마감 처리한다."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT promo_name, last_seen_date FROM promotions WHERE end_date IS NULL"
        ).fetchall()
        for row in rows:
            if row["promo_name"] not in seen_promo_names:
                conn.execute(
                    "UPDATE promotions SET end_date = ? WHERE promo_name = ?",
                    (row["last_seen_date"], row["promo_name"]),
                )


def apply_promotion_manual_overrides(db_path: str, overrides: dict, today: str) -> None:
    """config/promotions_manual.yaml 의 수동 보정값을 적용한다.

    이미 배너 스캔으로 발견된 기획전이면 start_date/end_date/url 을 덮어쓰고,
    스캔에 잡히지 않은(예: 앱 전용 등) 기획전이면 start_date 가 있을 때만 새로 만든다.
    """
    with _connect(db_path) as conn:
        for name, override in overrides.items():
            start_date = override.get("start_date")
            end_date = override.get("end_date")
            url = override.get("url")

            existing = conn.execute(
                "SELECT promo_name FROM promotions WHERE promo_name = ?", (name,)
            ).fetchone()

            if existing:
                sets, params = [], []
                if start_date:
                    sets.append("start_date = ?")
                    params.append(start_date)
                if end_date:
                    sets.append("end_date = ?")
                    params.append(end_date)
                if url:
                    sets.append("url = ?")
                    params.append(url)
                if sets:
                    params.append(name)
                    conn.execute(f"UPDATE promotions SET {', '.join(sets)} WHERE promo_name = ?", params)
            elif start_date:
                conn.execute(
                    "INSERT INTO promotions (promo_name, start_date, end_date, last_seen_date, url) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, start_date, end_date, end_date or today, url),
                )


def get_all_promotions(db_path: str) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT promo_name, start_date, end_date, last_seen_date, url FROM promotions"
        ).fetchall()
        return [dict(r) for r in rows]


def save_promotion_products(db_path: str, promo_name: str, products: list[dict]) -> None:
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO promotion_products (promo_name, brand, product_name) "
            "VALUES (?, ?, ?)",
            [(promo_name, p["brand"], p["product_name"]) for p in products],
        )


def get_active_promotions(db_path: str, as_of_date: str) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT promo_name, start_date, end_date, url FROM promotions "
            "WHERE start_date <= ? AND (end_date IS NULL OR end_date >= ?)",
            (as_of_date, as_of_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_promotion_products(db_path: str, promo_name: str) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT brand, product_name FROM promotion_products WHERE promo_name = ?",
            (promo_name,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_comment(db_path: str, date: str, comment_text: str, created_at: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO comments (date, comment_text, created_at, slack_sent) "
            "VALUES (?, ?, ?, 0) "
            "ON CONFLICT(date) DO UPDATE SET comment_text=excluded.comment_text, "
            "created_at=excluded.created_at",
            (date, comment_text, created_at),
        )


def mark_comment_sent(db_path: str, date: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("UPDATE comments SET slack_sent = 1 WHERE date = ?", (date,))
