from analysis.utils import norm_key
from storage.db import get_latest_date_before, get_rankings


def find_notable_entries(db_path: str, as_of_date: str, cfg: dict, exclude_keys: set | None = None) -> list[dict]:
    """전날 순위권(max_rank)에 없다가 오늘 top_n 이내로 갑자기 진입한 상품.

    exclude_keys 로 이미 기획전 영향으로 설명된 상품은 제외한다(중복 코멘트 방지).
    """
    thr = cfg["thresholds"]["notable_entry"]
    exclude_keys = exclude_keys or set()

    before_date = get_latest_date_before(db_path, as_of_date)
    prior_keys = (
        {norm_key(r["brand"], r["product_name"]) for r in get_rankings(db_path, before_date)}
        if before_date else set()
    )

    notable = []
    for r in get_rankings(db_path, as_of_date):
        if r["rank"] > thr["top_n"]:
            continue
        key = norm_key(r["brand"], r["product_name"])
        if key in prior_keys or key in exclude_keys:
            continue
        notable.append(r)

    return notable
