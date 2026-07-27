from storage.db import get_rankings


def find_seasonal_trends(db_path: str, as_of_date: str, cfg: dict) -> dict:
    """상위 top_n 내에서 동일 태그(계절/기능 속성) 상품이 min_count개 이상 동시 랭크되면 트렌드로 판단.

    반환: {tag: {"products": [...], "count": n}}
    """
    thr = cfg["thresholds"]["seasonal_trend"]
    tags_cfg = cfg["tags"]

    top_items = [r for r in get_rankings(db_path, as_of_date) if r["rank"] <= thr["top_n"]]

    tag_hits: dict[str, list[dict]] = {}
    for item in top_items:
        haystack = f"{item['brand']} {item['product_name']}".lower()
        for tag, keywords in tags_cfg.items():
            if any(kw.lower() in haystack for kw in keywords):
                tag_hits.setdefault(tag, []).append(item)

    return {tag: {"products": items, "count": len(items)}
            for tag, items in tag_hits.items() if len(items) >= thr["min_count"]}
