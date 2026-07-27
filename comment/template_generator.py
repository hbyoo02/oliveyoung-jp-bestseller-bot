from storage.db import OVERALL_CATEGORY


def generate_template_comment(facts: dict) -> str:
    """규칙 기반으로 코멘트를 조합한다 (외부 API 불필요).

    카테고리별 상시 베스트셀러/기획전 영향/트렌드는 데이터로 확정 가능해서 자동 서술하지만,
    특이 신규 진입 상품의 SNS 바이럴 여부나 큐텐/라쿠텐 순위 같은 건 코드가 확인할 방법이
    없으므로 사실을 지어내지 않고 "확인 필요" 라고만 표시한다 - 필요하면 사람이 직접 검색해서
    보완하는 걸 전제로 한다.
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
        lines.append("◦ SNS 바이럴 여부, 큐텐/라쿠텐 순위는 자동 확인이 안 돼서 직접 확인이 필요합니다.")

    if len(lines) == 2:
        lines.append("• 오늘은 특별히 눈에 띄는 순위 변동이 없었습니다.")

    return "\n".join(lines)
