from storage.db import OVERALL_CATEGORY


def generate_template_comment(facts: dict) -> str:
    """LLM 없이 규칙 기반으로 코멘트를 조합하는 폴백 생성기.

    Claude API 키가 없을 때만 쓰인다 - SNS/경쟁사 순위 조사 같은 서술형 분석은
    LLM 단계 전용이라 여기서는 데이터 요약만 담백하게 표시한다.
    """
    lines = [f"[{facts['date_label']}]", ""]

    for category, brands in facts["always_bestsellers_by_category"].items():
        label = "상시 베스트셀러" if category == OVERALL_CATEGORY else f"{category} 상시"
        lines.append(f"• {label} : {' / '.join(brands)}.")

    for promo in facts["promotion_impacts"]:
        brands = sorted({p["brand"] for p in promo["products"] if p["brand"]})
        names = " / ".join(brands) if brands else f"{promo['count']}개 제품"
        lines.append(f"• {promo['promo_name']} : 랭킹 내 {names} {promo['count']}개 제품 랭크.")

    for trend in facts["seasonal_trends"]:
        brands = sorted({p["brand"] for p in trend["products"] if p["brand"]})
        names = " / ".join(brands) if brands else f"{trend['count']}개 제품"
        lines.append(f"• {trend['tag']} 트렌드 : {names}.")

    for entry in facts["notable_entries"]:
        lines.append(f"• {entry['brand']} {entry['product_name']} : {entry['rank']}위로 신규 진입.")

    if len(lines) == 2:
        lines.append("• 오늘은 특별히 눈에 띄는 순위 변동이 없었습니다.")

    return "\n".join(lines)
