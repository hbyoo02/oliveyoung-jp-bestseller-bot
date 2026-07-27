def generate_template_comment(facts: dict) -> str:
    """LLM 없이 규칙 기반으로 코멘트를 조합하는 폴백 생성기."""
    lines = [f"[{facts['date_label']}]", ""]

    if facts["always_bestsellers"]:
        names = ", ".join(facts["always_bestsellers"])
        lines.append(f"• 상시 베스트셀러: {names}이(가) 꾸준히 상위권을 지키고 있습니다.")

    for promo in facts["promotion_impacts"]:
        lines.append(
            f"• {promo['promo_name']} 영향: 진행 중인 {promo['promo_name']} 기획전 효과로, "
            f"관련 제품이 베스트셀러 랭킹 내에 총 {promo['count']}개 올라와 있습니다."
        )

    for trend in facts["seasonal_trends"]:
        brands = sorted({p["brand"] for p in trend["products"] if p["brand"]})
        names = ", ".join(brands) if brands else f"{trend['count']}개 제품"
        lines.append(f"• {trend['tag']} 트렌드: {names} 제품이 상위권에 동시에 랭크되어 있습니다.")

    for entry in facts["notable_entries"]:
        lines.append(
            f"• 특이 신규 진입: {entry['brand']} {entry['product_name']}가 "
            f"{entry['rank']}위로 새롭게 진입했습니다."
        )

    if len(lines) == 2:
        lines.append("• 오늘은 특별히 눈에 띄는 순위 변동이 없었습니다.")

    return "\n".join(lines)
