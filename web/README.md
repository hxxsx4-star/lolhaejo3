# 전설이 도감 (웹)

봇 데이터(`utils/data.py`)에서 자동 생성되는 정적 전설이 도감 사이트입니다.

## 파일
- `dogam.html` — 완성된 도감 페이지 (그대로 열면 실제 전설이 이미지가 로드됩니다)
- `generate_dogam.py` — `utils/data.py`를 읽어 `dogam.html`을 다시 생성하는 스크립트

## 재생성 (전설이/장비 추가 후)
```bash
cd lolhaejo3
python web/generate_dogam.py      # web/dogam.html 갱신
```

## 열람 / 호스팅
- **로컬 확인**: `dogam.html`을 브라우저로 그냥 열면 됩니다.
- **간단 호스팅**: `python -m http.server` 로 `web/` 폴더를 서빙하거나,
  GitHub Pages / 정적 호스팅에 `dogam.html`을 올리면 링크로 공유됩니다.
- 이미지는 `utils/data.py`의 `PET_IMAGES` URL(ibb.co)을 직접 사용하므로 별도 자산이 필요 없습니다.
  (이미지가 안 뜨는 환경에서는 각 전설이의 이모지가 대신 표시됩니다.)
