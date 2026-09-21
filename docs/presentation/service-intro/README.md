# SalesLuv 화면별 서비스 소개서

한 화면 = 한 슬라이드, 15장. 웹 화면 캡처만 그림이고 제목·설명·주요 기능·사용 흐름·TIP 은
전부 PowerPoint 텍스트 상자라 열어서 바로 고칠 수 있다.

레이아웃·폰트·색·좌표는 `build_pptx.py` 상단 상수에 LOCK 되어 있고, 장마다 바뀌는 값은
`pages.json` 뿐이다. 한 장만 따로 디자인하는 일이 구조적으로 불가능하다.

## 만드는 순서

```sh
# 1. 캡처 (세션은 .auth.json 에 남아 다음부터 로그인 생략)
SALESLUV_ID=... SALESLUV_PW=... node capture.mjs [slug일부]

# 2. 문구 — pages.json 편집

# 3. 굽기
/usr/local/bin/python3.12 build_pptx.py      # out/SalesLuv_서비스소개서.pptx
/usr/local/bin/python3.12 check_layout.py    # out/check/*.png + 잘림·겹침 경고

# 4. 1920x1080 PNG 가 필요할 때만
DECK_SCALE=2 /usr/local/bin/python3.12 build_pptx.py   # out/...@2x.pptx
./export_png.sh                                        # out/png/*.png
```

아이콘을 추가하거나 고쳤을 때만 `node bake_icons.mjs` 로 `icons/*.png` 를 다시 굽는다.

## 규격

- 슬라이드 960×540 pt = PowerPoint Wide(13.333×7.5in). `1pt = 1px` 로 설계했다.
- Pretendard(`~/Library/Fonts`), Primary Blue `#2563EB`, 배경 `#FFFFFF`
- 화면 설명 최대 5개 / 주요 기능 3~4개 / 사용 흐름 3~4단계
- 캡처 뷰포트 1800×900(2:1). 웹 화면 카드 안쪽이 592×268 이라 왜곡 없이 거의 꽉 찬다.

## 검수

`check_layout.py` 는 pptx 도형을 PIL 로 직접 그린다. 이 환경엔 LibreOffice 가 없어
pptx 를 실제로 렌더할 수 없기 때문이다. 줄바꿈은 Pretendard 실측 폭으로 접으므로
글이 상자를 넘치면 잡힌다. 넘치면 레이아웃을 고치지 말고 `pages.json` 의 문구를 줄인다.

`out/check/*.png` 는 검수용 근사 렌더다. 최종 PNG 는 `export_png.sh` 가 Keynote 로 내보낸다
(이 환경엔 soffice 가 없어 Keynote 가 유일한 렌더 경로다). Keynote 의 슬라이드 이미지
내보내기는 `1pt = 1px` 라서 960×540 밖에 안 나오므로, `DECK_SCALE=2` 로 좌표와 글자를
통째로 2배 키운 `@2x.pptx` 를 만들어 내보낸다. 비율이 전부 같아 보이는 모습은 똑같다.
**배포용 pptx 는 `@2x` 가 아니라 `SalesLuv_서비스소개서.pptx` 다.**

`node_modules/playwright` 는 전역 설치본 심링크. `shots/`·`out/`·`.auth.json` 은 git 제외.
