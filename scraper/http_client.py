import logging
import time

import requests

logger = logging.getLogger("oy_bot.scraper")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_json(url: str, cfg: dict, params: dict | None = None):
    return _request(url, cfg, method="GET", params=params).json()


def fetch_text(url: str, cfg: dict, params: dict | None = None) -> str:
    return _request(url, cfg, method="GET", params=params).text


def fetch_json_post(url: str, cfg: dict, json_body: dict):
    return _request(url, cfg, method="POST", json_body=json_body).json()


def _request(url: str, cfg: dict, method: str, params: dict | None = None, json_body: dict | None = None):
    crawl_cfg = cfg["crawl"]
    timeout = crawl_cfg.get("request_timeout_sec", 15)
    max_retries = crawl_cfg.get("max_retries", 3)
    backoff = crawl_cfg.get("retry_backoff_sec", 2)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": crawl_cfg["base_url"] + "/",
    }
    # 실측 결과 langCode/dlvCntryCode 쿼리 파라미터만으로는 로케일이 결정되지 않고
    # (쿠키 없이 호출하면 영어로 응답함) 아래 쿠키가 있어야 일본어/JPY 응답이 온다.
    locale = crawl_cfg["locale_params"]
    cookies = {
        "dlvCntry": locale["dlvCntryCode"],
        "currency": "JPY",
        "curLang": locale["langCode"],
        "lang": locale["langCode"],
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(
                method, url, params=params, json=json_body,
                headers=headers, cookies=cookies, timeout=timeout,
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_error = e
            logger.warning("fetch failed (attempt %d/%d) for %s: %s", attempt, max_retries, url, e)
            if attempt < max_retries:
                time.sleep(backoff * attempt)

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_error}")
