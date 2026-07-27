import logging
import time

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("oy_bot.scraper")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_soup(url: str, cfg: dict) -> BeautifulSoup:
    crawl_cfg = cfg["crawl"]
    timeout = crawl_cfg.get("request_timeout_sec", 15)
    max_retries = crawl_cfg.get("max_retries", 3)
    backoff = crawl_cfg.get("retry_backoff_sec", 2)

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            last_error = e
            logger.warning("fetch failed (attempt %d/%d) for %s: %s", attempt, max_retries, url, e)
            if attempt < max_retries:
                time.sleep(backoff * attempt)

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_error}")
