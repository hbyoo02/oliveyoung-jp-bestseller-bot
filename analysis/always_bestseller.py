from storage.db import get_available_dates, get_rankings


def find_always_bestsellers(db_path: str, as_of_date: str, cfg: dict) -> list[str]:
    """최근 lookback_days 중 min_days_in_top 일 이상 top_rank 이내에 든 브랜드 목록."""
    thr = cfg["thresholds"]["always_bestseller"]
    dates = get_available_dates(db_path, before_or_on=as_of_date, limit=thr["lookback_days"])

    brand_day_count: dict[str, int] = {}
    for d in dates:
        brands_today = {
            r["brand"]
            for r in get_rankings(db_path, d)
            if r["rank"] <= thr["top_rank"] and r["brand"]
        }
        for brand in brands_today:
            brand_day_count[brand] = brand_day_count.get(brand, 0) + 1

    return sorted(b for b, c in brand_day_count.items() if c >= thr["min_days_in_top"])
