import json
import logging

from anthropic import Anthropic

logger = logging.getLogger("oy_bot.comment")

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """\
당신은 올리브영 재팬 베스트셀러 순위를 매일 분석하는 이커머스 MD입니다.
아래로 주어지는 분석 결과(JSON)를 바탕으로, 사람이 직접 순위를 보고 쓴 것처럼
자연스러운 한국어 존댓말 코멘트를 작성하세요.

규칙:
- 출력 형식은 "[date_label]" 제목 한 줄, 빈 줄, 그다음 "• "로 시작하는 불릿 항목들입니다.
- always_bestsellers, promotion_impacts, seasonal_trends, notable_entries 중
  데이터가 있는 항목만 코멘트에 포함하고, 비어 있는 항목은 언급하지 마세요.
- promotion_impacts 는 어떤 기획전 덕분에 몇 개 제품이 랭크되었는지 자연스럽게 설명하세요.
- seasonal_trends 는 왜 그런 트렌드가 나타났는지(계절/상황 수요) 짧게 해석을 덧붙이세요.
- notable_entries 는 왜 특이한지, viral 정보(checked=False면 "SNS 반응은 아직 확인되지 않았다"는
  취지로), 자유롭게 코멘트하세요.
- 문장은 예시보다 조금 더 풀어서 설명하듯 작성하되, 과장하지 말고 데이터에 기반해서만 서술하세요.
- 슬랙 mrkdwn 문법(*굵게*, 불릿 •, 줄바꿈)을 사용해도 좋습니다.
- 순수 텍스트만 출력하고, 다른 설명이나 머리말은 붙이지 마세요.
"""


def generate_llm_comment(facts: dict, api_key: str) -> str:
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False, indent=2)}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
