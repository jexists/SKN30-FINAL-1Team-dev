"""공지 본문 sanitize.

이 결과가 브라우저에서 그대로 innerHTML 이 되므로, 통과하면 안 되는 것을 하나씩 못박는다.
"""

import pytest

from app.services.html_sanitize import BodyEmpty, image_ids, sanitize_body

_IMAGE = "/notice-images/11111111-2222-3333-4444-555555555555"


def test_allowed_markup_survives():
    body = sanitize_body("<p><strong>공지</strong>입니다.</p><ul><li>첫째</li></ul>")
    assert body == "<p><strong>공지</strong>입니다.</p><ul><li>첫째</li></ul>"


def test_script_tag_is_removed():
    body = sanitize_body("<p>안녕</p><script>alert(1)</script>")
    assert "script" not in body
    assert "alert" not in body


def test_event_handler_attribute_is_removed():
    body = sanitize_body(f'<img src="{_IMAGE}" onerror="alert(1)">')
    assert "onerror" not in body
    assert _IMAGE in body


def test_javascript_href_is_removed():
    body = sanitize_body('<p><a href="javascript:alert(1)">누르기</a></p>')
    assert "javascript" not in body


def test_external_link_gets_noopener():
    body = sanitize_body('<p><a href="https://example.com">링크</a></p>')
    assert 'rel="noopener noreferrer"' in body


def test_image_outside_our_storage_is_dropped():
    body = sanitize_body('<p>본문</p><img src="https://evil.example/track.png">')
    assert "<img" not in body
    assert "evil.example" not in body


def test_relative_path_pretending_to_be_our_image_is_dropped():
    body = sanitize_body('<p>본문</p><img src="/notice-images/../../etc/passwd">')
    assert "<img" not in body


def test_data_uri_image_is_dropped():
    body = sanitize_body('<p>본문</p><img src="data:image/png;base64,AAAA">')
    assert "<img" not in body


def test_unknown_tag_is_unwrapped_but_text_stays():
    body = sanitize_body("<p>앞</p><marquee>가운데</marquee>")
    assert "marquee" not in body
    assert "가운데" in body


def test_body_that_becomes_empty_is_rejected():
    with pytest.raises(BodyEmpty):
        sanitize_body("<script>alert(1)</script>")


def test_whitespace_only_body_is_rejected():
    with pytest.raises(BodyEmpty):
        sanitize_body("<p>   </p>")


def test_image_only_body_is_allowed():
    """사진 한 장만 올린 공지도 본문으로 인정한다."""
    assert sanitize_body(f'<img src="{_IMAGE}">').startswith("<img")


def test_image_ids_are_collected_in_order_without_duplicates():
    other = "/notice-images/99999999-8888-7777-6666-555555555555"
    html = f'<img src="{_IMAGE}"><img src="{other}"><img src="{_IMAGE}">'
    assert image_ids(html) == [
        "11111111-2222-3333-4444-555555555555",
        "99999999-8888-7777-6666-555555555555",
    ]
