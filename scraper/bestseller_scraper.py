import logging

from scraper.http_client import fetch_soup

logger = logging.getLogger("oy_bot.scraper")


def fetch_bestsellers(cfg: dict) -> list[dict]:
    """올리브영 JP 베스트셀러 페이지에서 상위 max_rank개 상품을 수집한다.

    selectors 가 config.yaml 에 채워져 있어야 동작한다. (초기 상태는 빈 값)
    """
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["bestseller_url"]
    selectors = crawl_cfg["selectors"]["bestseller"]
    max_rank = crawl_cfg.get("max_rank", 100)

    if not url:
        raise ValueError(
            "crawl.bestseller_url 이 config.yaml 에 설정되지 않았습니다. "
            "실제 올리브영 JP 베스트셀러 URL을 입력해주세요."
        )
    if not selectors.get("item"):
        raise ValueError(
            "crawl.selectors.bestseller.item 이 설정되지 않았습니다. "
            "페이지 구조를 확인한 뒤 CSS 셀렉터를 채워주세요."
        )

    soup = fetch_soup(url, cfg)
    items = soup.select(selectors["item"])

    results = []
    for idx, item in enumerate(items[:max_rank], start=1):
        rank = _extract_rank(item, selectors.get("rank"), fallback=idx)
        brand = _extract_text(item, selectors.get("brand"))
        product_name = _extract_text(item, selectors.get("product_name"))

        if not product_name:
            logger.warning("rank %s: product_name 을 찾지 못했습니다 (셀렉터 확인 필요)", rank)
            continue

        results.append(
            {
                "rank": rank,
                "brand": brand or "",
                "product_name": product_name,
                "category": None,
            }
        )

    if not results:
        raise RuntimeError(
            "베스트셀러 상품을 하나도 찾지 못했습니다. 셀렉터 또는 페이지 구조를 확인해주세요."
        )

    return results


def _extract_text(item, selector: str | None) -> str | None:
    if not selector:
        return None
    el = item.select_one(selector)
    return el.get_text(strip=True) if el else None


def _extract_rank(item, selector: str | None, fallback: int) -> int:
    text = _extract_text(item, selector)
    if not text:
        return fallback
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else fallback
