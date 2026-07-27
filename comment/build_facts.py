from datetime import date

from sns.viral_check import check_viral

_WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def build_facts(
    as_of_date: str,
    always_bestsellers: list[str],
    promotion_impacts: dict,
    seasonal_trends: dict,
    notable_entries: list[dict],
) -> dict:
    d = date.fromisoformat(as_of_date)
    date_label = f"{d.month}월 {d.day}일({_WEEKDAY_KR[d.weekday()]}) 오전 베스트셀러"

    notable_with_viral = []
    for entry in notable_entries:
        viral = check_viral(entry["brand"], entry["product_name"])
        notable_with_viral.append({**entry, "viral": viral})

    return {
        "date_label": date_label,
        "always_bestsellers": always_bestsellers,
        "promotion_impacts": [
            {"promo_name": name, **data} for name, data in promotion_impacts.items()
        ],
        "seasonal_trends": [
            {"tag": tag, **data} for tag, data in seasonal_trends.items()
        ],
        "notable_entries": notable_with_viral,
    }
