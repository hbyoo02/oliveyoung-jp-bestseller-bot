import logging

from scraper.http_client import fetch_json

logger = logging.getLogger("oy_bot.scraper")


def fetch_bestsellers(cfg: dict) -> list[dict]:
    """전체(카테고리 무관) 베스트셀러 상위 max_rank개."""
    crawl_cfg = cfg["crawl"]
    return _fetch_ranking(cfg, ctgr_no="", max_rank=crawl_cfg.get("max_rank", 100))


def fetch_category_rankings(cfg: dict) -> dict[str, list[dict]]:
    """config.yaml 의 crawl.categories 에 정의된 카테고리별 베스트셀러 랭킹을 가져온다.

    반환: {카테고리명: [{"rank", "brand", "product_name"}, ...]}
    카테고리 하나가 실패해도 나머지는 계속 진행하고, 실패한 카테고리는 결과에서 빠진다.
    """
    crawl_cfg = cfg["crawl"]
    categories = crawl_cfg.get("categories") or {}
    max_rank = crawl_cfg.get("category_max_rank", 30)

    results = {}
    for name, ctgr_no in categories.items():
        try:
            results[name] = _fetch_ranking(cfg, ctgr_no=ctgr_no, max_rank=max_rank)
        except Exception:
            logger.exception("카테고리 '%s'(ctgrNo=%s) 랭킹 수집 실패, 건너뜁니다.", name, ctgr_no)

    return results


def _fetch_ranking(cfg: dict, ctgr_no: str, max_rank: int) -> list[dict]:
    """올리브영 JP(글로벌몰 일본 로케일) 베스트셀러 API 호출. 응답 배열의 순서가 곧 순위."""
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["base_url"] + crawl_cfg["api"]["bestseller_path"]
    locale = crawl_cfg["locale_params"]

    params = {
        "ctgrNo": ctgr_no,
        "acesCntryCode": locale["acesCntryCode"],
        "previewDate": "",
        "encKey": "",
        "encText": "",
        "accParam": "",
        "dispPageTypeCode": "30",
        "langCode": locale["langCode"],
        "dispPageNo": "",
        "mrgnCntryCode": locale["mrgnCntryCode"],
        "dlvCntryCode": locale["dlvCntryCode"],
        "isGlobal": "false",
        "showSoldoutProduct": "true",
    }

    data = fetch_json(url, cfg, params=params)
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"베스트셀러 API 응답이 비어있거나 예상한 형식이 아닙니다 (ctgrNo={ctgr_no!r}).")

    results = []
    for idx, item in enumerate(data[:max_rank], start=1):
        product_name = item.get("prdtName")
        if not product_name:
            logger.warning("rank %d: prdtName 이 없어 건너뜁니다", idx)
            continue
        results.append(
            {
                "rank": idx,
                "brand": item.get("brandName") or "",
                "product_name": product_name,
                "prdt_no": item.get("prdtNo"),
            }
        )

    if not results:
        raise RuntimeError(f"베스트셀러 상품을 하나도 파싱하지 못했습니다 (ctgrNo={ctgr_no!r}).")

    return results
