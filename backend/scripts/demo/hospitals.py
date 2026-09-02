"""공공데이터 병원 목록을 customer_company 에 넣을 수 있는 모양으로 정규화한다.

data/sample/hospital_list_공공데이터_v2.xlsx 는 8,306행 14컬럼이지만
customer_company 에 자리가 있는 것은 name·postcode·address·region_code 넷뿐이다.
전화번호·진료과목·병상수·좌표는 저장할 컬럼이 없어 버린다.

    uv run python -m scripts.demo.hospitals    # 자체 검사
"""

import re
from pathlib import Path
from typing import NamedTuple

from scripts.demo._xlsx import read_rows

# 저장소 루트의 고정 위치. 시더가 인자 없이 부를 수 있어야 한다.
SOURCE = (
    Path(__file__).resolve().parents[3] / "data" / "sample" / "hospital_list_공공데이터_v2.xlsx"
)

# 영업 대상만 넣는다. 폐업·휴업·전출 병원이 고객사 목록에 뜨면 화면이 거짓말을 한다.
OPEN_STATUS = "영업중"

# 주소 첫 토큰을 region_code 로 쓴다. 원본에 '삼성1동'·'625-9'·'82.0' 같은 주소 파편이
# 60여 종 섞여 있어 화이트리스트로 거른다. 원본이 쓰는 표기를 그대로 둔다.
REGIONS = (
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원특별자치도",
    "충청북도",
    "충청남도",
    "전북특별자치도",
    "전라남도",
    "경상북도",
    "경상남도",
    "제주특별자치도",
    # 원본이 광주광역시·전라남도를 이 이름으로 합쳐 두었다. 가공된 값이지만 1,347건이라
    # 버리면 지역 필터가 비어 보인다. 원본 표기를 보존한다.
    "전남광주통합특별시",
)

_POSTCODE = re.compile(r"^[0-9]{5}$")


class Hospital(NamedTuple):
    name: str
    postcode: str | None
    address: str | None
    region_code: str | None


def normalize_postcode(raw: str) -> str | None:
    """'3136.0' → '03136'. 5자리를 만들지 못하면 None.

    customer_company_postcode_check 가 ^[0-9]{5}$ 라 어긋난 값은 넣을 수 없다.
    원본의 42% 가 결측이므로 실패는 예외가 아니라 정상 경로다.
    """
    digits = raw.strip().split(".")[0]
    if not digits.isdigit():
        return None
    padded = digits.zfill(5)
    return padded if _POSTCODE.match(padded) else None


def normalize_region(address: str) -> str | None:
    """주소 첫 토큰이 광역시도일 때만 region_code 로 쓴다."""
    first = address.split(maxsplit=1)[0] if address else ""
    return first if first in REGIONS else None


def _district(address: str) -> str:
    """중복된 병원명을 구분할 '시·군·구'. 없으면 빈 문자열."""
    parts = address.split()
    if len(parts) >= 2 and parts[0] in REGIONS:
        wide = parts[0]
        for drop in ("특별자치도", "특별자치시", "특별시", "광역시", "통합특별시"):
            wide = wide.replace(drop, "")
        return f"{wide[:2]} {parts[1]}"
    return ""


def load(path: Path | str = SOURCE) -> list[Hospital]:
    """영업중 병원을 이름 충돌 없이 돌려준다.

    customer_company_team_name_uq 가 (team_id, name) 유일이라 중복 이름은 그대로
    넣을 수 없다. '우리병원' 17건처럼 겹치는 이름에는 지역을 붙이고, 그래도 겹치면
    번호를 붙인다. 원본 순서를 유지해 재실행 시 같은 이름이 나오게 한다.
    """
    hospitals: list[Hospital] = []
    used: set[str] = set()

    for row in read_rows(str(path)):
        if row.get("business_status", "").strip() != OPEN_STATUS:
            continue
        name = row.get("hospital_name", "").strip()
        if not name:
            continue

        address = (row.get("road_address") or row.get("lot_address") or "").strip() or None

        if name in used:
            district = _district(address or "")
            candidate = f"{name} ({district})" if district else name
            suffix = 2
            while candidate in used:
                candidate = f"{name} ({district}) {suffix}" if district else f"{name} {suffix}"
                suffix += 1
            name = candidate
        used.add(name)

        hospitals.append(
            Hospital(
                name=name,
                postcode=normalize_postcode(row.get("postal_code", "")),
                address=address,
                region_code=normalize_region(address or ""),
            )
        )
    return hospitals


def main() -> None:
    hospitals = load()
    names = [h.name for h in hospitals]

    assert len(names) == len(set(names)), "이름이 겹치면 customer_company 유일 인덱스에 걸린다"
    assert all(h.name.strip() for h in hospitals), "이름이 빈 행은 name CHECK 위반"
    assert all(h.postcode is None or _POSTCODE.match(h.postcode) for h in hospitals), (
        "postcode 는 5자리 숫자이거나 NULL 이어야 한다"
    )
    assert all(h.region_code is None or h.region_code in REGIONS for h in hospitals)
    assert load() == hospitals, "같은 입력에 같은 결과가 나와야 재실행이 안전하다"

    with_postcode = sum(1 for h in hospitals if h.postcode)
    with_region = sum(1 for h in hospitals if h.region_code)
    renamed = sum(1 for h in hospitals if h.name.endswith(")") or h.name[-1].isdigit())
    print(f"영업중 병원      {len(hospitals):>6}")
    print(f"  postcode 있음  {with_postcode:>6} ({with_postcode * 100 // len(hospitals)}%)")
    print(f"  region 있음    {with_region:>6} ({with_region * 100 // len(hospitals)}%)")
    print(f"  이름 보정      {renamed:>6}")
    print("자체 검사 통과")


if __name__ == "__main__":
    main()
