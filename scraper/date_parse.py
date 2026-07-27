import re
from datetime import date


_RANGE_PATTERNS = [
    # 2026.07.20 - 2026.08.03 / 2026-07-20~2026-08-03
    re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2}).{0,3}?(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"),
    # 7/20(월)~8/3(월) / 7.20~8.3
    re.compile(r"(\d{1,2})[./](\d{1,2}).{0,6}?[~\-〜～](\d{1,2})[./](\d{1,2})"),
    # 7月20日(月)〜8月3日(月)
    re.compile(r"(\d{1,2})月(\d{1,2})日.{0,6}?[~\-〜～](\d{1,2})月(\d{1,2})日"),
]


def parse_period_text(text: str, today: date | None = None) -> tuple[str | None, str | None]:
    """기획전 기간 텍스트를 (start_date, end_date) 'YYYY-MM-DD' 튜플로 파싱한다.

    연도가 표기되지 않은 경우 today 기준 연도를 사용한다 (해가 바뀌는 경우는
    수동 매핑 파일(config/promotions_manual.yaml)로 보정 필요).
    파싱 실패 시 (None, None) 반환.
    """
    if not text:
        return None, None
    today = today or date.today()

    m = _RANGE_PATTERNS[0].search(text)
    if m:
        y1, mo1, d1, y2, mo2, d2 = map(int, m.groups())
        return _safe_iso(y1, mo1, d1), _safe_iso(y2, mo2, d2)

    for pattern in _RANGE_PATTERNS[1:]:
        m = pattern.search(text)
        if m:
            mo1, d1, mo2, d2 = map(int, m.groups())
            year = today.year
            start = _safe_iso(year, mo1, d1)
            end = _safe_iso(year, mo2, d2)
            return start, end

    return None, None


def _safe_iso(y: int, mo: int, d: int) -> str | None:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None
