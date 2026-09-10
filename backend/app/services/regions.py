"""주소에서 지역 코드를 정한다.

지역 코드는 프론트 shared/regionCodes.ts 와 같은 17개다. 다르면 지역별 실적이 맞물리지
않는다. 회사를 만드는 경로가 넷(직접·명함·등록증·엑셀)이라 부르는 쪽마다 채우게 두지 않고
저장 시점에 한 번만 정한다.
"""

# 주소 앞머리와 코드. 긴 앞머리를 먼저 봐야 "충청북도" 가 "충남" 규칙에 걸리지 않는다.
_SIDO_PREFIXES: tuple[tuple[str, str], ...] = (
    ("서울특별시", "seoul"),
    ("서울", "seoul"),
    ("부산광역시", "busan"),
    ("부산", "busan"),
    ("대구광역시", "daegu"),
    ("대구", "daegu"),
    ("인천광역시", "incheon"),
    ("인천", "incheon"),
    ("광주광역시", "gwangju"),
    ("광주", "gwangju"),
    ("대전광역시", "daejeon"),
    ("대전", "daejeon"),
    ("울산광역시", "ulsan"),
    ("울산", "ulsan"),
    ("세종특별자치시", "sejong"),
    ("세종", "sejong"),
    ("경기도", "gyeonggi"),
    ("경기", "gyeonggi"),
    ("강원특별자치도", "gangwon"),
    ("강원도", "gangwon"),
    ("강원", "gangwon"),
    ("충청북도", "chungbuk"),
    ("충북", "chungbuk"),
    ("충청남도", "chungnam"),
    ("충남", "chungnam"),
    ("전북특별자치도", "jeonbuk"),
    ("전라북도", "jeonbuk"),
    ("전북", "jeonbuk"),
    ("전라남도", "jeonnam"),
    ("전남", "jeonnam"),
    ("경상북도", "gyeongbuk"),
    ("경북", "gyeongbuk"),
    ("경상남도", "gyeongnam"),
    ("경남", "gyeongnam"),
    ("제주특별자치도", "jeju"),
    ("제주", "jeju"),
)


def region_code_from_address(address: str | None) -> str | None:
    """주소 앞머리의 시·도로 지역 코드를 정한다. 못 알아보면 None(미지정)이다.

    틀린 지역이 들어가는 것보다 비어 있는 편이 낫다. 팀장이 회사 정보에서 고칠 수 있다.
    """
    if not address:
        return None
    head = address.lstrip()
    for prefix, code in _SIDO_PREFIXES:
        if head.startswith(prefix):
            return code
    return None


def _self_check() -> None:
    assert region_code_from_address("서울시 서초구 남부순환로 339길 23") == "seoul"
    assert region_code_from_address("  경기도 성남시 분당구") == "gyeonggi"
    assert region_code_from_address("충청북도 청주시") == "chungbuk"
    assert region_code_from_address("전북특별자치도 전주시") == "jeonbuk"
    assert region_code_from_address(None) is None
    assert region_code_from_address("") is None
    assert region_code_from_address("합성시 관계구 세일즈로 20") is None
    print("regions self-check ok")


if __name__ == "__main__":
    _self_check()
