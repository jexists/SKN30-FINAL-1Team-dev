"""표준 라이브러리만으로 .xlsx 를 읽는다.

openpyxl 을 의존성에 추가하지 않으려고 둔다. 시더가 엑셀을 한 번 읽는 것이 전부인데
그것 때문에 모든 배포에 패키지를 하나 더 얹을 이유가 없다. xlsx 는 XML 을 담은 zip 이라
zipfile 과 ElementTree 로 충분하다.

읽기 전용이며 수식·서식·병합셀은 다루지 않는다. 값이 있는 셀만 꺼낸다.
"""

import re
import zipfile
from xml.etree import ElementTree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_COLUMN = re.compile(r"[A-Z]+")


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    """sharedStrings.xml 의 문자열 표. 셀이 t="s" 면 이 표의 색인을 담는다."""
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
    # 한 <si> 가 서식 때문에 <t> 여러 개로 쪼개지므로 이어 붙인다.
    return ["".join(t.text or "" for t in si.iter(f"{NS}t")) for si in root.iter(f"{NS}si")]


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "s":
        value = cell.find(f"{NS}v")
        if value is None or value.text is None:
            return ""
        index = int(value.text)
        return shared[index] if index < len(shared) else ""
    if kind == "inlineStr":
        inline = cell.find(f"{NS}is")
        return "".join(t.text or "" for t in inline.iter(f"{NS}t")) if inline is not None else ""
    value = cell.find(f"{NS}v")
    return value.text or "" if value is not None else ""


def read_rows(path: str, sheet_index: int = 0) -> list[dict[str, str]]:
    """첫 행을 열 이름으로 삼아 나머지 행을 dict 로 돌려준다.

    빈 셀은 키가 아예 없는 것이 아니라 빈 문자열로 채운다. 호출부가 결측을
    `row["col"]` 로 바로 다룰 수 있어야 한다.
    """
    with zipfile.ZipFile(path) as book:
        shared = _shared_strings(book)
        names = book.namelist()
        target = f"xl/worksheets/sheet{sheet_index + 1}.xml"
        if target not in names:
            raise ValueError(f"{path} 에 {target} 이 없습니다.")

        rows: list[dict[str, str]] = []
        header: dict[str, str] = {}
        for row in ElementTree.fromstring(book.read(target)).iter(f"{NS}row"):
            cells: dict[str, str] = {}
            for cell in row.iter(f"{NS}c"):
                reference = cell.get("r") or ""
                match = _COLUMN.match(reference)
                if match is None:
                    continue
                cells[match.group()] = _cell_text(cell, shared)
            if not header:
                header = {column: text for column, text in cells.items() if text}
                continue
            rows.append({name: cells.get(column, "") for column, name in header.items()})
        return rows
