import html
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
