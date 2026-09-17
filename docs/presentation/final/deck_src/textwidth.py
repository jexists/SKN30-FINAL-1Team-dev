"""Pretendard 글자 폭을 macOS CoreText 로 실제로 잰다 (inch).

어림짐작 대신 Keynote 가 쓰는 것과 같은 폰트 엔진에 물어본다.
한 줄로 끝나야 하는 글상자가 줄바꿈되어 카드 밖으로 새는 것을 빌드와 검수 양쪽에서 막는다.
"""

import ctypes
import ctypes.util
from ctypes import byref, c_double, c_long, c_void_p

_cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
_ct = ctypes.CDLL(ctypes.util.find_library("CoreText"))

_cf.CFStringCreateWithCString.restype = c_void_p
_cf.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, ctypes.c_uint32]
_cf.CFDictionaryCreate.restype = c_void_p
_cf.CFDictionaryCreate.argtypes = [c_void_p, c_void_p, c_void_p, c_long, c_void_p, c_void_p]
_cf.CFAttributedStringCreate.restype = c_void_p
_cf.CFAttributedStringCreate.argtypes = [c_void_p, c_void_p, c_void_p]
_cf.CFRelease.argtypes = [c_void_p]

_ct.CTFontCreateWithName.restype = c_void_p
_ct.CTFontCreateWithName.argtypes = [c_void_p, c_double, c_void_p]
_ct.CTLineCreateWithAttributedString.restype = c_void_p
_ct.CTLineCreateWithAttributedString.argtypes = [c_void_p]
_ct.CTLineGetTypographicBounds.restype = c_double
_ct.CTLineGetTypographicBounds.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p]

_FONT = c_void_p.in_dll(_ct, "kCTFontAttributeName")
_KCB = c_void_p.in_dll(_cf, "kCFTypeDictionaryKeyCallBacks")
_VCB = c_void_p.in_dll(_cf, "kCFTypeDictionaryValueCallBacks")
_UTF8 = 0x08000100

# base.py 의 weight → 실제 Pretendard 패밀리
FAMILY = {400: "Pretendard", 500: "Pretendard Medium",
          600: "Pretendard SemiBold", 700: "Pretendard Bold"}


def _cfstr(text):
    return _cf.CFStringCreateWithCString(None, text.encode(), _UTF8)


def width(text, pt, weight=400):
    """한 줄로 그렸을 때의 폭 (inch)."""
    font = _ct.CTFontCreateWithName(_cfstr(FAMILY.get(weight, "Pretendard")),
                                    c_double(pt), None)
    keys = (c_void_p * 1)(_FONT)
    vals = (c_void_p * 1)(font)
    attrs = _cf.CFDictionaryCreate(None, keys, vals, 1, byref(_KCB), byref(_VCB))
    line = _ct.CTLineCreateWithAttributedString(
        _cf.CFAttributedStringCreate(None, _cfstr(text), attrs))
    return _ct.CTLineGetTypographicBounds(line, None, None, None) / 72.0


if __name__ == "__main__":   # 자기 점검 — 렌더에서 실제로 줄바꿈된 문구가 칸보다 넓어야 한다
    assert width("DB 없이 조회 값 고정 · RAG 호출까지 측정", 15) > 3.45
    assert width("충족 · 누락 · 왜곡 + 오류 출처 · 중대 오류", 15) < 3.45
    assert width("Won 227", 20, 700) > width("Won 227", 20, 400)   # 한글은 고정폭
    print("ok")
