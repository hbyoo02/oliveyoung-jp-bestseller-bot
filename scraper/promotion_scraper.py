import logging
from pathlib import Path

import yaml

from scraper.http_client import fetch_soup

logger = logging.getLogger("oy_bot.scraper")


def fetch_promotion_banners(cfg: dict) -> list[dict]:
    """홈페이지 캐러셀에서 현재 떠 있는 기획전 배너 목록을 수집한다.

    기획전은 고정 URL이 없고 매일/매주 바뀌므로, 이 함수는 "오늘 시점에 어떤
    기획전이 떠 있는가"만 알려준다. 시작/종료일 추적은 storage.db 의
    upsert_promotion_seen / close_missing_promotions 가 첫 발견일 기준으로 처리한다.

    반환: [{"promo_name": str, "url": str | None}, ...]
    """
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["homepage_url"]
    selectors = crawl_cfg["selectors"]["promotion_banner"]

    if not url:
        raise ValueError("crawl.homepage_url 이 config.yaml 에 설정되지 않았습니다.")
    if not selectors.get("item"):
        raise ValueError("crawl.selectors.promotion_banner.item 이 설정되지 않았습니다.")

    soup = fetch_soup(url, cfg)
    banners = []
    for item in soup.select(selectors["item"]):
        title_el = item.select_one(selectors.get("title", ""))
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        link_el = item.select_one(selectors.get("link", "")) or item
        link = link_el.get("href") if link_el else None
        if link and link.startswith("/"):
            link = _join_url(url, link)

        banners.append({"promo_name": title, "url": link})

    return banners


def fetch_promotion_products(cfg: dict, promo: dict) -> list[dict]:
    """기획전 랜딩 페이지에서 대상 브랜드/상품 목록을 best-effort 로 수집한다.

    셀렉터가 없거나 페이지 구조가 안 맞아 실패하면 수동 매핑 파일을 사용한다.
    """
    selectors = cfg["crawl"]["selectors"]["promotion_detail"]
    manual = _load_manual_promotion_products().get(promo["promo_name"])

    if not selectors.get("product_item") or not promo.get("url"):
        if manual:
            return manual
        logger.info(
            "'%s' 기획전은 자동 수집 셀렉터/URL이 없고 수동 매핑도 없습니다. "
            "config/promotion_products_manual.yaml 에 추가해주세요.",
            promo["promo_name"],
        )
        return []

    try:
        soup = fetch_soup(promo["url"], cfg)
    except Exception as e:
        logger.warning("기획전 랜딩 페이지 수집 실패 (%s): %s", promo["promo_name"], e)
        return manual or []

    products = []
    for item in soup.select(selectors["product_item"]):
        brand_el = item.select_one(selectors.get("brand", ""))
        name_el = item.select_one(selectors.get("product_name", ""))
        brand = brand_el.get_text(strip=True) if brand_el else ""
        name = name_el.get_text(strip=True) if name_el else None
        if name:
            products.append({"brand": brand, "product_name": name})

    return products or (manual or [])


def _join_url(base_url: str, path: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base_url, path)


def _load_manual_promotion_products() -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / "promotion_products_manual.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
