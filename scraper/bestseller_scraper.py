import logging

from scraper.http_client import fetch_json

logger = logging.getLogger("oy_bot.scraper")


def fetch_bestsellers(cfg: dict) -> list[dict]:
    """올리브영 JP(글로벌몰 일본 로케일) 베스트셀러 API에서 상위 max_rank개 상품을 가져온다.

    응답 배열의 순서가 곧 순위이다(별도 rank 필드 없음).
    """
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["base_url"] + crawl_cfg["api"]["bestseller_path"]
    locale = crawl_cfg["locale_params"]
    max_rank = crawl_cfg.get("max_rank", 100)

    params = {
        "ctgrNo": "",
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
        raise RuntimeError("베스트셀러 API 응답이 비어있거나 예상한 형식이 아닙니다.")

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
                "category": None,
            }
        )

    if not results:
        raise RuntimeError("베스트셀러 상품을 하나도 파싱하지 못했습니다.")

    return results
