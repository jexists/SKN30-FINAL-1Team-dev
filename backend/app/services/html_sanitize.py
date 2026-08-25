"""공지 본문 HTML 에서 허용한 것만 남긴다.

이 결과는 브라우저에서 그대로 innerHTML 이 된다(프론트 NoticeDrawer). 저장형 XSS 를 막는
방어선이 여기 하나뿐이므로 단순화를 이유로 느슨하게 두지 않는다.

편집기(프론트 components/RichTextEditor)도 valid_elements 로 태그를 좁히지만 그건 화면의
편의다. API 는 편집기를 거치지 않은 요청도 받으므로 저장 직전에 서버가 다시 자른다.
두 허용목록은 한 쌍이다. 한쪽만 넓히면 화면에서 넣은 것이 저장할 때 조용히 사라진다.
"""

import re

import nh3

_TAGS: set[str] = {
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "ul",
    "ol",
    "li",
    "blockquote",
    "h2",
    "h3",
    "h4",
    "a",
    "img",
}
_ATTRIBUTES: dict[str, set[str]] = {
    # rel 은 두지 않는다. link_rel 이 noopener 를 직접 붙이므로 nh3 가 허용을 거부한다.
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height"},
}
# 사진은 저장소에 올리고 본문에는 내부 참조만 둔다. data: 를 열면 본문이 통째로 커지고
# 사진마다 다른 검사 경로가 생기므로 받지 않는다.
_URL_SCHEMES: set[str] = {"http", "https", "mailto"}

# 본문이 가리킬 수 있는 사진 주소. POST /api/notices/images 가 돌려주는 모양 그대로다.
NOTICE_IMAGE_PREFIX = "/notice-images/"
_IMAGE_SRC = re.compile(
    r"^/notice-images/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_ATTR = re.compile(r"""\bsrc\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


class BodyEmpty(ValueError):
    """태그를 다 벗기고 나니 글자가 하나도 남지 않았다."""


def _drop_foreign_images(html: str) -> str:
    """우리 저장소가 아닌 사진을 버린다.

    nh3 는 스킴만 보고 경로 모양은 보지 못한다. 상대 경로는 스킴이 없어 그대로 통과하므로
    `/notice-images/{uuid}` 가 아닌 src 는 여기서 걷어낸다. 외부 주소를 그리면 열람자
    아이피가 그쪽으로 새고, 사진이 언제든 다른 것으로 바뀔 수 있다.
    """

    def keep(match: re.Match[str]) -> str:
        src = _SRC_ATTR.search(match.group(0))
        if src is not None and _IMAGE_SRC.match(src.group(1)):
            return match.group(0)
        return ""

    return _IMG_TAG.sub(keep, html)


def strip_tags(html: str) -> str:
    """태그를 모두 벗긴 글자만 남긴다. 본문이 비었는지 볼 때 쓴다."""
    return nh3.clean(html, tags=set())


def sanitize_body(html: str) -> str:
    """허용목록 밖을 전부 잘라낸 HTML 을 돌려준다. 남는 글자가 없으면 BodyEmpty 다."""
    cleaned = _drop_foreign_images(
        nh3.clean(
            html,
            tags=_TAGS,
            attributes=_ATTRIBUTES,
            url_schemes=_URL_SCHEMES,
            link_rel="noopener noreferrer",
            strip_comments=True,
        )
    )
    # notice.body 에 btrim(body) <> '' CHECK 가 걸려 있다. 사진만 있는 본문은 허용한다.
    if strip_tags(cleaned).strip() == "" and NOTICE_IMAGE_PREFIX not in cleaned:
        raise BodyEmpty
    return cleaned


def image_ids(html: str) -> list[str]:
    """본문이 가리키는 사진 id 를 처음 나온 순서대로 돌려준다. 중복은 한 번만 센다."""
    found: dict[str, None] = {}
    for tag in _IMG_TAG.findall(html):
        src = _SRC_ATTR.search(tag)
        if src is not None and _IMAGE_SRC.match(src.group(1)):
            found[src.group(1).removeprefix(NOTICE_IMAGE_PREFIX)] = None
    return list(found)
