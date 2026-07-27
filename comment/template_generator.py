from comment.korean import josa
from storage.db import OVERALL_CATEGORY


def generate_template_comment(facts: dict, cfg: dict) -> str:
    """규칙 기반으로, 사람이 풀어쓴 것 같은 문장 형태의 코멘트를 조합한다 (외부 API 불필요).

    카테고리별 상시 베스트셀러/기획전 영향/트렌드는 데이터로 확정 가능해서 문장으로 서술하지만,
    특이 신규 진입 상품의 SNS 바이럴 여부나 큐텐/라쿠텐 순위 같은 건 코드가 확인할 방법이
    없으므로 사실을 지어내지 않고 "직접 확인이 필요하다"고만 표시한다.
    """
    top_rank = cfg["thresholds"]["always_bestseller"]["top_rank"]
    tag_labels = cfg.get("tag_labels") or {}
    tag_reasons = cfg.get("tag_reasons") or {}

    blocks = []

    for category, brands in facts["always_bestsellers_by_category"].items():
        blocks.append(_always_bestseller_sentence(category, brands, top_rank))

    for promo in facts["promotion_impacts"]:
        blocks.append(_promotion_sentence(promo))

    for trend in facts["seasonal_trends"]:
        blocks.append(_trend_sentence(trend, tag_labels, tag_reasons))

    for entry in facts["notable_entries"]:
        blocks.append(_notable_entry_sentence(entry))

    if not blocks:
        blocks.append("• 오늘은 특별히 눈에 띄는 순위 변동이 없었습니다.")

    return f"[{facts['date_label']}]\n\n" + "\n\n".join(blocks)


def _always_bestseller_sentence(category: str, brands: list[str], top_rank: int) -> str:
    joined = ", ".join(brands)
    if category == OVERALL_CATEGORY:
        particle = josa(brands[-1], "이", "가")
        return f"• 상시 베스트셀러: {joined}{particle} 이번 주에도 꾸준히 {top_rank}위권을 지키고 있습니다."
    return f"• {category} 상시: {joined} 등이 꾸준히 상위권에 랭크되고 있습니다."


def _promotion_sentence(promo: dict) -> str:
    promo_name = promo["promo_name"]
    products = promo["products"]
    brands = sorted({p["brand"] for p in products if p["brand"]})
    brand_text = ", ".join(brands[:3]) + (" 등" if len(brands) > 3 else "")

    new_entries = [p for p in products if p["rank_before"] is None]

    if len(new_entries) == len(products):
        # 대상 상품이 전부 이번에 처음 랭크된 경우 - 담백하게 신규 진입만 서술
        return f"• {promo_name}: {brand_text} 제품이 랭킹에 새롭게 진입했습니다."

    extra = (
        " 기획전 시작 전에는 순위권 밖이었던 제품들도 다수 포함되어 있어, 이번 기획전의 영향이 뚜렷해 보입니다."
        if new_entries
        else " 기존에도 상위권이었던 제품들의 순위가 한층 더 올라, 이번 기획전의 효과가 뚜렷해 보입니다."
    )
    return (
        f"• {promo_name} 영향: 현재 진행 중인 {promo_name} 기획전 효과로, {brand_text} 제품이 "
        f"베스트셀러 랭킹 내에 총 {promo['count']}개나 올라와 있습니다.{extra}"
    )


def _trend_sentence(trend: dict, tag_labels: dict, tag_reasons: dict) -> str:
    label = tag_labels.get(trend["tag"], trend["tag"])
    reason = tag_reasons.get(trend["tag"], "")
    brands = sorted({p["brand"] for p in trend["products"] if p["brand"]})
    brand_text = ", ".join(brands)
    reason_sentence = f" {reason}" if reason else ""
    return f"• {label} 트렌드: {brand_text} 제품이 상위권에 함께 랭크되어 있습니다.{reason_sentence}"


def _notable_entry_sentence(entry: dict) -> str:
    particle = josa(entry["product_name"], "이", "가")
    return (
        f"• {entry['brand']} {entry['product_name']}{particle} {entry['rank']}위로 새롭게 진입했습니다. "
        "SNS 바이럴 여부나 큐텐·라쿠텐 순위는 자동으로 확인하지 못해 직접 확인이 필요합니다."
    )
