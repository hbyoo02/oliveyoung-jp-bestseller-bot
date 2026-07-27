import json
from pathlib import Path


def export_latest_comment(docs_dir: Path, date: str, comment_text: str, generated_at: str) -> None:
    """GitHub Pages 정적 페이지(docs/index.html)가 읽는 latest.json 을 갱신한다."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    payload = {"date": date, "comment": comment_text, "generated_at": generated_at}
    with open(docs_dir / "latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
