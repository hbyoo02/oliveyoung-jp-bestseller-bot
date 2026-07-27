import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from analysis.always_bestseller import find_always_bestsellers
from analysis.notable_entries import find_notable_entries
from analysis.promotion_impact import find_promotion_impacts
from analysis.seasonal_trend import find_seasonal_trends
from analysis.utils import norm_key
from comment.build_facts import build_facts
from comment.llm_generator import generate_llm_comment
from comment.template_generator import generate_template_comment
from config.settings import (
    ANTHROPIC_API_KEY,
    CONFIG,
    DB_PATH,
    LOG_DIR,
    MANUAL_PROMOTIONS_PATH,
    SLACK_WEBHOOK_URL,
)
from notify.slack import send_to_slack
from scraper.bestseller_scraper import fetch_bestsellers
from scraper.promotion_scraper import fetch_promotion_banners, fetch_promotion_products
from storage.db import (
    apply_promotion_manual_overrides,
    close_missing_promotions,
    init_db,
    mark_comment_sent,
    save_comment,
    save_promotion_products,
    save_rankings,
    upsert_promotion_seen,
)

logger = logging.getLogger("oy_bot")

KST = ZoneInfo("Asia/Seoul")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
        ],
    )


def run() -> None:
    setup_logging()
    init_db(DB_PATH)

    today = datetime.now(KST).date().isoformat()
    logger.info("=== 올리브영 JP 베스트셀러 모니터링 시작: %s ===", today)

    try:
        bestsellers = fetch_bestsellers(CONFIG)
        save_rankings(DB_PATH, today, bestsellers)
        logger.info("베스트셀러 %d개 저장 완료", len(bestsellers))
    except Exception:
        logger.exception("베스트셀러 크롤링 실패. 오늘 분석을 진행할 수 없습니다.")
        return

    try:
        banners = fetch_promotion_banners(CONFIG)
        for banner in banners:
            upsert_promotion_seen(DB_PATH, banner["promo_name"], today, banner["url"])
        close_missing_promotions(DB_PATH, {b["promo_name"] for b in banners}, today)

        for banner in banners:
            products = fetch_promotion_products(CONFIG, banner)
            if products:
                save_promotion_products(DB_PATH, banner["promo_name"], products)

        logger.info("기획전 배너 %d개 확인 완료", len(banners))
    except Exception:
        logger.exception("기획전 배너 크롤링 실패. 기존 저장된 기획전 데이터로 계속 진행합니다.")

    apply_promotion_manual_overrides(DB_PATH, _load_manual_promotions(), today)

    always_bestsellers = find_always_bestsellers(DB_PATH, today, CONFIG)
    promotion_impacts = find_promotion_impacts(DB_PATH, today, CONFIG)
    seasonal_trends = find_seasonal_trends(DB_PATH, today, CONFIG)

    impacted_keys = {
        norm_key(p["brand"], p["product_name"])
        for data in promotion_impacts.values()
        for p in data["products"]
    }
    notable_entries = find_notable_entries(DB_PATH, today, CONFIG, exclude_keys=impacted_keys)

    facts = build_facts(today, always_bestsellers, promotion_impacts, seasonal_trends, notable_entries)

    comment_text = _generate_comment(facts)
    logger.info("생성된 코멘트:\n%s", comment_text)

    save_comment(DB_PATH, today, comment_text, datetime.now(KST).isoformat())

    if send_to_slack(SLACK_WEBHOOK_URL, comment_text):
        mark_comment_sent(DB_PATH, today)
        logger.info("Slack 전송 완료")
    else:
        logger.error("Slack 전송 실패 (코멘트는 DB에 백업됨: date=%s)", today)


def _load_manual_promotions() -> dict:
    if not MANUAL_PROMOTIONS_PATH.exists():
        return {}
    with open(MANUAL_PROMOTIONS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _generate_comment(facts: dict) -> str:
    if ANTHROPIC_API_KEY:
        try:
            return generate_llm_comment(facts, ANTHROPIC_API_KEY)
        except Exception:
            logger.exception("Claude API 코멘트 생성 실패, 템플릿 기반으로 대체합니다.")
    return generate_template_comment(facts)


if __name__ == "__main__":
    run()
