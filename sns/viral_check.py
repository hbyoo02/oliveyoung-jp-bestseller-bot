"""SNS(인스타그램/틱톡) 바이럴 체크 인터페이스.

1단계에서는 실제 연동을 구현하지 않고 인터페이스만 정의한다 (사용자 결정).
추후 확장 시 아래 중 한 방식으로 check_viral() 내부만 교체하면 된다:
  - 웹 검색 기반 해시태그/언급량 추정
  - 서드파티 소셜 리스닝 API(Brand24, Talkwalker 등) 연동 (사용자 API 키 필요)
"""


def check_viral(brand: str, product_name: str) -> dict:
    return {
        "checked": False,
        "is_viral": None,
        "note": "SNS 바이럴 체크는 1단계에서 미구현 (추후 확장 예정)",
    }
