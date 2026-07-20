# 전설이 키우기 웹앱 설치 가이드

디스코드로 로그인해서 웹에서 전설이를 돌보고(밥/샤워/산책), 원정·일일퀘스트를
수령하고, 실시간 랭킹을 보는 웹사이트입니다. 봇과 같은 DB·게임 로직을 공유합니다.

## 1. 디스코드 OAuth 설정 (한 번만)
1. https://discord.com/developers/applications → 봇과 **같은 애플리케이션** 선택
2. 왼쪽 **OAuth2** 메뉴 → **Redirects**에 추가:
   `http://서버외부IP:8080/callback`
3. 같은 페이지의 **Client ID** 와 **Client Secret**(Reset Secret으로 발급) 확인

## 2. config.ini 에 [web] 섹션 추가 (VM에서 직접 수정)
```ini
[web]
client_id = 클라이언트ID
client_secret = 클라이언트시크릿
redirect_uri = http://서버외부IP:8080/callback
secret_key = 아무_긴_무작위_문자열_(세션암호화용)
port = 8080
admin_ids = 111111111111111111, 222222222222222222
```
`admin_ids` : 웹 관리자 패널(🛠️ 관리자 탭)을 쓸 수 있는 디스코드 유저 ID를
쉼표로 구분해 나열합니다. (비워두면 관리자 패널은 아무에게도 안 보입니다)
디스코드 개발자 모드 → 본인 우클릭 → "ID 복사"로 얻을 수 있습니다.
secret_key 생성 예: `python3 -c "import secrets; print(secrets.token_hex(32))"`

## 3. 의존성 설치
```bash
cd ~/lolhaejo3
source venv/bin/activate
pip install -r requirements.txt
```

## 4. GCP 방화벽 8080 포트 열기 (한 번만)
GCP 콘솔 → VPC 네트워크 → 방화벽 → 규칙 만들기:
- 대상: 네트워크의 모든 인스턴스 / 소스 IP: 0.0.0.0/0 / TCP: 8080
또는 Cloud Shell에서:
```bash
gcloud compute firewall-rules create allow-legendweb --allow tcp:8080
```

## 5. 실행
### 임시 실행 (테스트)
```bash
cd ~/lolhaejo3 && source venv/bin/activate
uvicorn webapp.app:app --host 0.0.0.0 --port 8080
```
브라우저에서 `http://서버외부IP:8080` 접속 → 디스코드로 로그인!

### 상시 실행 (systemd 등록, 권장)
```bash
sudo cp ~/lolhaejo3/deploy/legendweb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now legendweb
```
- 상태 확인: `sudo systemctl status legendweb`
- 재시작: `sudo systemctl restart legendweb`  (git pull 후 이거 한 줄)
- 로그: `journalctl -u legendweb -f`

## 구조
- `webapp/app.py` — FastAPI 서버 (OAuth 로그인·대시보드·액션 API·랭킹)
- `webapp/templates/` — 페이지 (base/index/me)
- 게임 규칙 수정은 `utils/game.py` 한 곳만 고치면 봇·웹 동시 반영

## 참고
- 랭킹 이름은 웹에 한 번이라도 로그인한 유저만 표시됩니다 (그 외 "모험가#뒷자리").
- 봇과 웹은 별개 프로세스라, 같은 유저가 두 곳을 정확히 동시에 조작하는 극히
  드문 경우 스탯 변경 하나가 덮일 수 있습니다. 아이템/포인트는 원자 연산이라 안전합니다.
