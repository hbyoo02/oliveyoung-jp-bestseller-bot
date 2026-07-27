import logging
from pathlib import Path

import yaml

from scraper.date_parse import parse_period_text
from scraper.http_client import fetch_soup

logger = logging.getLogger("oy_bot.scraper")


def fetch_promotions(cfg: dict) -> list[dict]:
    """진행 중인 기획전 목록을 수집한다. 각 항목: promo_name, start_date, end_date, url.

    기간 텍스트 파싱에 실패하면 start_date/end_date 가 None 으로 남는데,
    이 경우 config/promotions_manual.yaml 에 수동으로 채워 넣어야 한다.
    """
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["promotion_url"]
    selectors = crawl_cfg["selectors"]["promotion"]

    if not url:
        raise ValueError(
            "crawl.promotion_url 이 config.yaml 에 설정되지 않았습니다."
        )
    if not selectors.get("list_item"):
        raise ValueError(
            "crawl.selectors.promotion.list_item 이 설정되지 않았습니다."
        )

    soup = fetch_soup(url, cfg)
    items = soup.select(selectors["list_item"])

    promotions = []
    for item in items:
        name_el = item.select_one(selectors.get("promo_name", ""))
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            continue

        link_el = item.select_one(selectors.get("promo_link", ""))
        link = link_el.get("href") if link_el else None

        period_el = item.select_one(selectors.get("promo_period_text", ""))
        period_text = period_el.get_text(strip=True) if period_el else ""
        start_date, end_date = parse_period_text(period_text)

        promotions.append(
            {
                "promo_name": name,
                "start_date": start_date,
                "end_date": end_date,
                "url": link,
            }
        )

    return _apply_manual_overrides(promotions)


def fetch_promotion_products(cfg: dict, promo: dict) -> list[dict]:
    """기획전 상세 페이지에서 대상 브랜드/상품 목록을 수집한다.

    자동 수집 셀렉터가 없거나 실패하면 수동 매핑 파일에서 가져온다.
    """
    selectors = cfg["crawl"]["selectors"]["promotion"]
    manual = _load_manual_promotion_products().get(promo["promo_name"])

    if not selectors.get("detail_product_item") or not promo.get("url"):
        if manual:
            return manual
        logger.warning(
            "'%s' 기획전의 대상 상품 셀렉터/URL이 없고 수동 매핑도 없습니다.",
            promo["promo_name"],
        )
        return []

    try:
        soup = fetch_soup(promo["url"], cfg)
    except Exception as e:
        logger.warning("기획전 상세 페이지 수집 실패 (%s): %s", promo["promo_name"], e)
        return manual or []

    products = []
    for item in soup.select(selectors["detail_product_item"]):
        brand_el = item.select_one(selectors.get("detail_brand", ""))
        name_el = item.select_one(selectors.get("detail_product_name", ""))
        brand = brand_el.get_text(strip=True) if brand_el else ""
        name = name_el.get_text(strip=True) if name_el else None
        if name:
            products.append({"brand": brand, "product_name": name})

    return products or (manual or [])


def _manual_paths():
    root = Path(__file__).resolve().parent.parent / "config"
    return root / "promotions_manual.yaml", root / "promotion_products_manual.yaml"


def _apply_manual_overrides(promotions: list[dict]) -> list[dict]:
    promo_path, _ = _manual_paths()
    if not promo_path.exists():
        return promotions

    with open(promo_path, "r", encoding="utf-8") as f:
        overrides = yaml.safe_load(f) or {}

    by_name = {p["promo_name"]: p for p in promotions}
    for name, override in overrides.items():
        if name in by_name:
            by_name[name].update({k: v for k, v in override.items() if v is not None})
        else:
            by_name[name] = {"promo_name": name, "url": None, **override}

    return list(by_name.values())


def _load_manual_promotion_products() -> dict:
    _, products_path = _manual_paths()
    if not products_path.exists():
        return {}
    with open(products_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
