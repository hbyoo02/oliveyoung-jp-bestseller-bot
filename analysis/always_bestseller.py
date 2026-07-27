from storage.db import OVERALL_CATEGORY, get_available_dates, get_rankings


def find_always_bestsellers_by_category(db_path: str, as_of_date: str, cfg: dict) -> dict[str, list[str]]:
    """전체 랭킹 + config.yaml 에 설정된 카테고리별로 '상시 베스트셀러' 브랜드를 계산한다.

    브랜드가 하나도 없는(즉 최근 turnover가 커서 꾸준한 브랜드가 없는) 카테고리는 결과에서
    빠진다 - 코멘트에서 "OO 상시: (없음)" 같은 빈 항목이 나오지 않도록.

    반환: {카테고리명: [브랜드, ...]} (카테고리명은 "전체" 포함)
    """
    thr = cfg["thresholds"]["always_bestseller"]

    result: dict[str, list[str]] = {}
    overall = _consistent_brands(db_path, as_of_date, OVERALL_CATEGORY, thr)
    if overall:
        result[OVERALL_CATEGORY] = overall

    for name in (cfg["crawl"].get("categories") or {}):
        brands = _consistent_brands(db_path, as_of_date, name, thr)
        if brands:
            result[name] = brands

    return result


def _consistent_brands(db_path: str, as_of_date: str, category: str, thr: dict) -> list[str]:
    """최근 lookback_days 중 min_days_in_top 일 이상 top_rank 이내에 든 브랜드 목록."""
    dates = get_available_dates(db_path, category=category, before_or_on=as_of_date, limit=thr["lookback_days"])

    brand_day_count: dict[str, int] = {}
    for d in dates:
        brands_today = {
            r["brand"]
            for r in get_rankings(db_path, d, category=category)
            if r["rank"] <= thr["top_rank"] and r["brand"]
        }
        for brand in brands_today:
            brand_day_count[brand] = brand_day_count.get(brand, 0) + 1

    return sorted(b for b, c in brand_day_count.items() if c >= thr["min_days_in_top"])
