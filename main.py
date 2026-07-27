import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from analysis.always_bestseller import find_always_bestsellers_by_category
from analysis.notable_entries import find_notable_entries
from analysis.promotion_impact import find_promotion_impacts
from analysis.seasonal_trend import find_seasonal_trends
from analysis.utils import norm_key
from comment.build_facts import build_facts
from comment.export_web import export_latest_comment
from comment.llm_generator import generate_llm_comment
from comment.template_generator import generate_template_comment
from config.settings import ANTHROPIC_API_KEY, CONFIG, DB_PATH, DOCS_DIR, LOG_DIR, SLACK_WEBHOOK_URL
from notify.slack import send_to_slack
from scraper.bestseller_scraper import fetch_bestsellers, fetch_category_rankings
from scraper.promotion_scraper import fetch_promotion_products, fetch_promotions
from storage.db import (
    OVERALL_CATEGORY,
    init_db,
    mark_comment_sent,
    save_comment,
    save_promotion_products,
    save_promotions,
    save_rankings,
)

logger = logging.getLogger("oy_bot")

KST = ZoneInfo("Asia/Seoul")


def setup_logging() -> None:
    # Windows 콘솔 기본 코드페이지(cp949 등)는 일본어를 못 그려 콘솔 출력이 깨지므로 강제 UTF-8.
    # logging.StreamHandler() 기본값은 stderr 이므로 둘 다 재설정해야 한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

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
        save_rankings(DB_PATH, today, OVERALL_CATEGORY, bestsellers)
        logger.info("전체 베스트셀러 %d개 저장 완료", len(bestsellers))
    except Exception:
        logger.exception("베스트셀러 크롤링 실패. 오늘 분석을 진행할 수 없습니다.")
        return

    category_rankings = fetch_category_rankings(CONFIG)
    for category, items in category_rankings.items():
        save_rankings(DB_PATH, today, category, items)
    logger.info("카테고리별 베스트셀러 %d개 카테고리 저장 완료", len(category_rankings))

    try:
        promotions = fetch_promotions(CONFIG)
        save_promotions(DB_PATH, promotions)
        for promo in promotions:
            products = fetch_promotion_products(CONFIG, promo)
            if products:
                save_promotion_products(DB_PATH, promo["promo_name"], products)
        logger.info("기획전 %d개 저장 완료", len(promotions))
    except Exception:
        logger.exception("기획전 크롤링 실패. 기존 저장된 기획전 데이터로 계속 진행합니다.")

    always_bestsellers_by_category = find_always_bestsellers_by_category(DB_PATH, today, CONFIG)
    promotion_impacts = find_promotion_impacts(DB_PATH, today, CONFIG)
    seasonal_trends = find_seasonal_trends(DB_PATH, today, CONFIG)

    impacted_keys = {
        norm_key(p["brand"], p["product_name"])
        for data in promotion_impacts.values()
        for p in data["products"]
    }
    notable_entries = find_notable_entries(DB_PATH, today, CONFIG, exclude_keys=impacted_keys)

    facts = build_facts(
        today, always_bestsellers_by_category, promotion_impacts, seasonal_trends, notable_entries
    )

    comment_text = _generate_comment(facts)
    logger.info("생성된 코멘트:\n%s", comment_text)

    generated_at = datetime.now(KST).isoformat()
    save_comment(DB_PATH, today, comment_text, generated_at)
    export_latest_comment(DOCS_DIR, today, comment_text, generated_at)

    if not SLACK_WEBHOOK_URL:
        logger.info("SLACK_WEBHOOK_URL 미설정 - Slack 전송 없이 코멘트만 생성/저장했습니다.")
    elif send_to_slack(SLACK_WEBHOOK_URL, comment_text):
        mark_comment_sent(DB_PATH, today)
        logger.info("Slack 전송 완료")
    else:
        logger.error("Slack 전송 실패 (코멘트는 DB에 백업됨: date=%s)", today)


def _generate_comment(facts: dict) -> str:
    if ANTHROPIC_API_KEY:
        try:
            return generate_llm_comment(facts, ANTHROPIC_API_KEY)
        except Exception:
            logger.exception("Claude API 코멘트 생성 실패, 템플릿 기반으로 대체합니다.")
    return generate_template_comment(facts)


if __name__ == "__main__":
    run()
