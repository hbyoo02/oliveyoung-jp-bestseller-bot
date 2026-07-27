import sqlite3
from contextlib import contextmanager
from pathlib import Path

OVERALL_CATEGORY = "전체"

SCHEMA = """
CREATE TABLE IF NOT EXISTS rankings (
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    rank INTEGER NOT NULL,
    brand TEXT NOT NULL,
    product_name TEXT NOT NULL,
    PRIMARY KEY (date, category, rank)
);

CREATE TABLE IF NOT EXISTS promotions (
    promo_name TEXT PRIMARY KEY,
    start_date TEXT NOT NULL,
    end_date TEXT,
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


def save_rankings(db_path: str, date: str, category: str, items: list[dict]) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM rankings WHERE date = ? AND category = ?", (date, category))
        conn.executemany(
            "INSERT INTO rankings (date, category, rank, brand, product_name) "
            "VALUES (:rank_date, :category, :rank, :brand, :product_name)",
            [
                {
                    "rank_date": date,
                    "category": category,
                    "rank": item["rank"],
                    "brand": item["brand"],
                    "product_name": item["product_name"],
                }
                for item in items
            ],
        )


def get_rankings(db_path: str, date: str, category: str = OVERALL_CATEGORY) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT rank, brand, product_name FROM rankings "
            "WHERE date = ? AND category = ? ORDER BY rank", (date, category)
        ).fetchall()
        return [dict(r) for r in rows]


def get_available_dates(
    db_path: str, category: str = OVERALL_CATEGORY, before_or_on: str | None = None, limit: int = 30
) -> list[str]:
    with _connect(db_path) as conn:
        if before_or_on:
            rows = conn.execute(
                "SELECT DISTINCT date FROM rankings WHERE category = ? AND date <= ? "
                "ORDER BY date DESC LIMIT ?", (category, before_or_on, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT date FROM rankings WHERE category = ? "
                "ORDER BY date DESC LIMIT ?", (category, limit)
            ).fetchall()
        return [r["date"] for r in rows]


def get_latest_date_before(db_path: str, date: str, category: str = OVERALL_CATEGORY) -> str | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM rankings WHERE date < ? AND category = ?", (date, category)
        ).fetchone()
        return row["d"] if row and row["d"] else None


def save_promotions(db_path: str, promotions: list[dict]) -> None:
    """기획전 목록을 upsert한다. start_date/end_date 는 CMS API가 제공하는 정확한 게시
    기간(또는 config/promotions_manual.yaml 의 수동 보정값)을 그대로 사용한다."""
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO promotions (promo_name, start_date, end_date, url) "
            "VALUES (:promo_name, :start_date, :end_date, :url) "
            "ON CONFLICT(promo_name) DO UPDATE SET "
            "start_date=excluded.start_date, end_date=excluded.end_date, url=excluded.url",
            promotions,
        )


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
