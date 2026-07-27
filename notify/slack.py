import logging
import time

import requests

logger = logging.getLogger("oy_bot.slack")

MAX_RETRIES = 3
BACKOFF_BASE_SEC = 2


def send_to_slack(webhook_url: str, comment_text: str) -> bool:
    """Slack Incoming Webhook 으로 코멘트를 전송한다. 최종 실패 시 False 반환(예외를 던지지 않음)."""
    if not webhook_url:
        logger.error("SLACK_WEBHOOK_URL 이 설정되지 않아 Slack 전송을 건너뜁니다.")
        return False

    payload = {"text": comment_text}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            logger.warning(
                "Slack 전송 실패 (attempt %d/%d): status=%s body=%s",
                attempt, MAX_RETRIES, response.status_code, response.text,
            )
        except requests.RequestException as e:
            logger.warning("Slack 전송 중 예외 (attempt %d/%d): %s", attempt, MAX_RETRIES, e)

        if attempt < MAX_RETRIES:
            time.sleep(BACKOFF_BASE_SEC * (2 ** (attempt - 1)))

    logger.error("Slack 전송 최종 실패 (%d회 시도). 코멘트는 DB에 백업되어 있습니다.", MAX_RETRIES)
    return False
