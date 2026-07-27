import html
import logging
import re
from datetime import date
from pathlib import Path

import yaml

from scraper.http_client import fetch_json, fetch_json_post, fetch_text

logger = logging.getLogger("oy_bot.scraper")

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_NO_END_SENTINEL = "29991231"


def fetch_promotions(cfg: dict) -> list[dict]:
    """홈페이지 main-vue-data API에서 캐러셀 배너의 기획전 정보를 가져온다.

    각 배너는 CMS에 등록된 정확한 dispStartYmd/dispEndYmd(게시 시작/종료일)를 이미
    갖고 있어 기간 텍스트를 파싱할 필요가 없다. 게시 기간이 thresholds.promotion_detection
    .max_duration_days 보다 길면 상시성 배너로 보고 제외한다.

    반환: [{"promo_name": str, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "url": str|None}]
    """
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["base_url"] + crawl_cfg["api"]["main_vue_data_path"]
    locale = crawl_cfg["locale_params"]
    max_duration = cfg["thresholds"]["promotion_detection"]["max_duration_days"]
    target_corners = set(crawl_cfg.get("promotion_corner_numbers") or [])

    params = {
        "previewDate": "",
        "encKey": "",
        "encText": "",
        "acesCntryCode": locale["acesCntryCode"],
        "accParam": "",
        "langCode": locale["langCode"],
        "dispPageNo": "",
        "mrgnCntryCode": locale["mrgnCntryCode"],
        "dlvCntryCode": locale["dlvCntryCode"],
    }

    data = fetch_json(url, cfg, params=params)
    corners = data.get("cornerList", []) if isinstance(data, dict) else []

    promotions: dict[str, dict] = {}
    for corner in corners:
        if not corner:
            continue
        if target_corners and corner.get("dispPageConrNo") not in target_corners:
            continue
        for set_val in (corner.get("setContsMap") or {}).values():
            if not set_val:
                continue
            entry = _extract_entry(set_val, max_duration)
            if entry:
                promotions[entry["promo_name"]] = entry

    return _apply_manual_overrides(list(promotions.values()))


def _flatten(value) -> list[dict]:
    """IMAGE/TEXT 필드는 응답에 따라 list, {contsTgtNo: [...]} dict, 또는 아예 없을 수 있다."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [item for group in value.values() for item in group]
    return []


def _extract_entry(set_val: dict, max_duration_days: int) -> dict | None:
    images = _flatten(set_val.get("IMAGE"))
    texts = _flatten(set_val.get("TEXT"))
    items = images + texts
    if not items:
        return None

    start_date = _ymd_to_iso(next((i.get("dispStartYmd") for i in items if i.get("dispStartYmd")), None))
    end_date = _ymd_to_iso(next((i.get("dispEndYmd") for i in items if i.get("dispEndYmd")), None))
    if not start_date or not end_date:
        return None  # 날짜 정보 없는 섹션(상시 카테고리 바로가기 등)은 기획전으로 취급하지 않음
    if (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days > max_duration_days:
        return None  # 장기간 게시되는 상시성 배너로 간주하고 제외

    name = None
    for img in images:
        alt = img.get("contsPcAltrnText") or img.get("contsAltrnText")
        if alt and _is_meaningful_name(alt):
            name = alt.strip()
            break
    if not name:
        for t in texts:
            cleaned = _strip_html(t.get("contsCont", ""))
            if cleaned and _is_meaningful_name(cleaned):
                name = cleaned
                break
    if not name:
        return None

    promo_url = next((i.get("contsUrl") for i in items if i.get("contsUrl")), None)
    if promo_url and promo_url.startswith("/"):
        promo_url = "https://global.oliveyoung.com" + promo_url

    return {"promo_name": name, "start_date": start_date, "end_date": end_date, "url": promo_url}


def _ymd_to_iso(ymd: str | None) -> str | None:
    if not ymd or len(ymd) != 8 or ymd == _NO_END_SENTINEL:
        return None
    try:
        return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])).isoformat()
    except ValueError:
        return None


def _strip_html(text: str) -> str:
    unescaped = html.unescape(text)
    return _HTML_TAG_RE.sub(" ", unescaped).strip()


_PUNCT_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)


def _is_meaningful_name(name: str) -> bool:
    """alt 텍스트가 '.' 같은 자리표시자가 아니라 실제 기획전명인지 대략적으로 걸러낸다."""
    stripped = name.strip()
    return len(stripped) >= 2 and not _PUNCT_ONLY_RE.match(stripped)


_PRDT_NO_RE = re.compile(r"prdtNo=([A-Za-z0-9]+)")


def fetch_promotion_products(cfg: dict, promo: dict) -> list[dict]:
    """기획전 대상 상품 목록을 최대한 자동으로 알아낸다.

    파이프라인 (실측으로 확인됨):
      1. 기획전 랜딩 페이지 HTML에서 상품 링크(prdtNo)를 몇 개 뽑는다.
      2. 그 상품들의 브랜드 ID(brandNo)를 /product/detail-data 로 조회한다.
      3. 확인된 브랜드마다 /display/page/brand/product-list 로 그 브랜드의 전체 상품
         목록을 가져온다 - 캠페인 페이지에 실제로 이미지가 걸린 몇 개 상품뿐 아니라
         해당 브랜드가 랭킹에 올린 상품 전체를 "기획전 영향" 판단 대상으로 삼기 위함.

    자동 수집이 실패하거나 상품이 하나도 안 잡히면 config/promotion_products_manual.yaml
    수동 매핑으로 보완한다(자동 수집 결과와 합쳐진다).
    """
    manual = _load_manual_promotion_products().get(promo["promo_name"]) or []

    auto: list[dict] = []
    if promo.get("url"):
        try:
            auto = _resolve_products_via_landing_page(cfg, promo["url"])
        except Exception:
            logger.exception("'%s' 기획전 랜딩 페이지에서 상품 자동 수집 실패", promo["promo_name"])

    merged = _merge_products(auto, manual)
    if not merged:
        logger.info(
            "'%s' 기획전의 대상 상품을 찾지 못했습니다 (자동 수집 결과 없음, 수동 매핑도 없음). "
            "필요하면 config/promotion_products_manual.yaml 에 추가해주세요.",
            promo["promo_name"],
        )
    else:
        logger.info("'%s' 기획전 대상 상품 %d개 확보 (자동 %d + 수동 %d)",
                     promo["promo_name"], len(merged), len(auto), len(manual))
    return merged


def _resolve_products_via_landing_page(cfg: dict, landing_url: str) -> list[dict]:
    mapping_cfg = cfg["thresholds"]["promotion_product_mapping"]
    max_lookups = mapping_cfg["max_products_to_resolve"]

    page_html = fetch_text(landing_url, cfg)
    prdt_nos = list(dict.fromkeys(_PRDT_NO_RE.findall(page_html)))  # dedupe, preserve order
    if not prdt_nos:
        return []

    products: dict[str, dict] = {}
    brand_nos: set[str] = set()
    for prdt_no in prdt_nos[:max_lookups]:
        try:
            info = _fetch_product_brand_info(cfg, prdt_no)
        except Exception:
            logger.warning("prdtNo=%s 상품 정보 조회 실패, 건너뜁니다.", prdt_no)
            continue
        if info.get("brand_no"):
            brand_nos.add(info["brand_no"])
        if info.get("product_name"):
            products[prdt_no] = {
                "prdt_no": prdt_no,
                "brand": info.get("brand") or "",
                "product_name": info["product_name"],
            }

    for brand_no in brand_nos:
        try:
            for p in _fetch_brand_products(cfg, brand_no):
                products[p["prdt_no"]] = p
        except Exception:
            logger.warning("brandNo=%s 브랜드 상품 목록 조회 실패, 건너뜁니다.", brand_no)

    return list(products.values())


def _fetch_product_brand_info(cfg: dict, prdt_no: str) -> dict:
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["base_url"] + crawl_cfg["api"]["product_detail_path"]
    locale = crawl_cfg["locale_params"]
    body = {
        "prdtNo": prdt_no,
        "langCode": locale["langCode"],
        "dlvCntryCode": locale["dlvCntryCode"],
        "mrgnCntryCode": locale["mrgnCntryCode"],
        "acesCntryCode": locale["acesCntryCode"],
    }
    data = fetch_json_post(url, cfg, body)
    product = (data or {}).get("product") or {}
    return {
        "brand_no": product.get("brandNo"),
        "brand": product.get("brandName"),
        "product_name": product.get("prdtName"),
    }


def _fetch_brand_products(cfg: dict, brand_no: str) -> list[dict]:
    crawl_cfg = cfg["crawl"]
    url = crawl_cfg["base_url"] + crawl_cfg["api"]["brand_product_list_path"]
    locale = crawl_cfg["locale_params"]
    mapping_cfg = cfg["thresholds"]["promotion_product_mapping"]

    params = {
        "pageNum": 1,
        "rowsPerPage": mapping_cfg["brand_catalog_page_size"],
        "brandNo": brand_no,
        "prdtSortStdrCode": 10,
        "acesCntryCode": locale["acesCntryCode"],
    }
    data = fetch_json(url, cfg, params=params)
    items = (data or {}).get("list") or []

    return [
        {"prdt_no": item["prdtNo"], "brand": item.get("brandName") or "", "product_name": item["prdtName"]}
        for item in items
        if item.get("prdtNo") and item.get("prdtName")
    ]


def _merge_products(auto: list[dict], manual: list[dict]) -> list[dict]:
    by_key: dict = {}
    for p in auto + manual:
        key = p.get("prdt_no") or (p.get("brand", ""), p.get("product_name", ""))
        by_key[key] = p
    return list(by_key.values())


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
        base = by_name.get(name, {"promo_name": name, "start_date": None, "end_date": None, "url": None})
        base.update({k: v for k, v in override.items() if v is not None})
        by_name[name] = base

    # 시작일이 없는 항목은 만들 수 없으므로 제외
    return [p for p in by_name.values() if p.get("start_date")]


def _load_manual_promotion_products() -> dict:
    _, products_path = _manual_paths()
    if not products_path.exists():
        return {}
    with open(products_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
