from datetime import date

from analysis.utils import norm_key
from storage.db import (
    get_active_promotions,
    get_latest_date_before,
    get_promotion_products,
    get_rankings,
)


def find_promotion_impacts(db_path: str, as_of_date: str, cfg: dict) -> dict:
    """진행 중인 기획전 중, 스펙에 정의된 조건을 만족하는 상품만 '기획전 영향'으로 판단한다.

    반환: {promo_name: {"products": [...], "count": n}}
    """
    thr = cfg["thresholds"]["promotion_impact"]
    as_of = date.fromisoformat(as_of_date)

    results = {}
    for promo in get_active_promotions(db_path, as_of_date):
        if not promo["start_date"]:
            continue

        elapsed = (as_of - date.fromisoformat(promo["start_date"])).days
        if elapsed < thr["min_elapsed_days"]:
            continue

        products = get_promotion_products(db_path, promo["promo_name"])
        if not products:
            continue

        before_date = get_latest_date_before(db_path, promo["start_date"])
        before_by_prdt, before_by_key = _rankings_lookups(db_path, before_date) if before_date else ({}, {})
        after_by_prdt, after_by_key = _rankings_lookups(db_path, as_of_date)

        matched = []
        seen_after_keys = set()  # 자동+수동 매핑이 같은 상품을 중복으로 잡는 경우 방지
        for p in products:
            after = None
            if p.get("prdt_no") and p["prdt_no"] in after_by_prdt:
                after = after_by_prdt[p["prdt_no"]]
            else:
                key = norm_key(p["brand"], p["product_name"])
                after = after_by_key.get(key)
            if after is None:
                continue

            dedupe_key = norm_key(after["brand"], after["product_name"])
            if dedupe_key in seen_after_keys:
                continue
            seen_after_keys.add(dedupe_key)

            if p.get("prdt_no") and p["prdt_no"] in before_by_prdt:
                before = before_by_prdt[p["prdt_no"]]
            else:
                before = before_by_key.get(norm_key(after["brand"], after["product_name"]))
            rank_before = before["rank"] if before else None

            if _is_impact(rank_before, after["rank"], thr):
                matched.append(
                    {
                        "brand": after["brand"],
                        "product_name": after["product_name"],
                        "rank_before": rank_before,
                        "rank_after": after["rank"],
                    }
                )

        if matched:
            results[promo["promo_name"]] = {"products": matched, "count": len(matched)}

    return results


def _is_impact(rank_before: int | None, rank_after: int, thr: dict) -> bool:
    if rank_before is not None:
        # 케이스 1: 전에도 상위권(20위 이내)이었는데, 5위 이내로 추가 상승
        if rank_before <= thr["already_top_before_rank"] and rank_after <= thr["surge_to_rank"] \
                and rank_after < rank_before:
            return True
        # 케이스 2: 전에는 100위 이내였는데, 50위 이상 급상승
        if rank_before <= thr["midrange_before_max_rank"] \
                and (rank_before - rank_after) >= thr["midrange_min_jump"]:
            return True
        return False

    # 케이스 3: 전에는 100위 밖(=랭킹 데이터 없음) -> 상위권 신규 진입
    return rank_after <= thr["new_entry_after_max_rank"]


def _rankings_lookups(db_path: str, date_str: str) -> tuple[dict, dict]:
    """(prdt_no -> row, norm_key -> row) 두 조회 테이블을 함께 만든다."""
    by_prdt: dict = {}
    by_key: dict = {}
    for r in get_rankings(db_path, date_str):
        row = {"rank": r["rank"], "brand": r["brand"], "product_name": r["product_name"]}
        if r.get("prdt_no"):
            by_prdt[r["prdt_no"]] = row
        by_key[norm_key(r["brand"], r["product_name"])] = row
    return by_prdt, by_key
