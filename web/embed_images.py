"""dogam.html 안의 외부 이미지(ibb.co)를 data URI(base64)로 박아 넣어
어디서 열어도 이미지가 보이는 자체완결형 파일을 만듭니다.

▶ 인터넷이 되는 곳에서 실행하세요 (본인 PC 또는 봇이 도는 VM):
    python web/embed_images.py
결과: web/dogam_offline.html  (이 파일 하나만 있으면 이미지까지 전부 표시됨)
"""
import os
import re
import base64
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "dogam.html")
OUT = os.path.join(HERE, "dogam_offline.html")


def guess_mime(url: str) -> str:
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext == ".webp":
        return "image/webp"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".gif":
        return "image/gif"
    return "image/png"


def main():
    html = open(SRC, encoding="utf-8").read()
    urls = sorted(set(re.findall(r'https://i\.ibb\.co/[^\s"\'<>]+', html)))
    print(f"이미지 {len(urls)}개 임베드 시작...")

    ok = 0
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=25).read()
            b64 = base64.b64encode(data).decode()
            html = html.replace(u, f"data:{guess_mime(u)};base64,{b64}")
            ok += 1
            print(f"  ✔ {u}  ({len(data):,} bytes)")
        except Exception as e:
            print(f"  [실패] {u}  ({e})")

    open(OUT, "w", encoding="utf-8").write(html)
    print(f"\n완료: {ok}/{len(urls)}개 임베드 → {OUT}")
    print("이제 dogam_offline.html 을 어디서 열든 이미지가 보입니다.")


if __name__ == "__main__":
    main()
