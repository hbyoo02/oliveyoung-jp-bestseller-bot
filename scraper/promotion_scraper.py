import logging
import re
from datetime import date
from pathlib import Path

import yaml

from scraper.http_client import fetch_json

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
        if target_corners and corner.get("dispPageConrNo") not in target_corners:
            continue
        for set_val in (corner.get("setContsMap") or {}).values():
            entry = _extract_entry(set_val, max_duration)
            if entry:
                promotions[entry["promo_name"]] = entry

    return _apply_manual_overrides(list(promotions.values()))


def _extract_entry(set_val: dict, max_duration_days: int) -> dict | None:
    images = set_val.get("IMAGE") or []
    text_groups = set_val.get("TEXT") or {}
    texts = [t for group in text_groups.values() for t in group]
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
        if alt:
            name = alt.strip()
            break
    if not name:
        for t in texts:
            cleaned = _strip_html(t.get("contsCont", ""))
            if cleaned:
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
    return _HTML_TAG_RE.sub(" ", text).replace("&amp;", "&").strip()


def fetch_promotion_products(cfg: dict, promo: dict) -> list[dict]:
    """기획전 대상 상품 목록. 랜딩 페이지 구조가 캠페인마다 달라 자동 수집하지 않고,
    config/promotion_products_manual.yaml 수동 매핑만 사용한다.
    """
    manual = _load_manual_promotion_products().get(promo["promo_name"])
    if not manual:
        logger.info(
            "'%s' 기획전의 대상 상품이 수동 매핑에 없습니다. "
            "config/promotion_products_manual.yaml 에 추가해주세요.",
            promo["promo_name"],
        )
    return manual or []


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
