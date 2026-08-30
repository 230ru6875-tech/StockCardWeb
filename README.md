# StockCardWeb

GitHub Pages + GitHub Actions 기반 주식 카드 대시보드입니다.

- 브라우저에는 API 키를 저장하지 않습니다.
- GitHub Actions가 서버 측에서 데이터를 수집해 `data/latest.json`을 갱신합니다.
- GitHub Pages는 `index.html`이 `data/latest.json`을 읽어 카드로 표시합니다.

## 필요한 GitHub Actions Secrets

`Settings > Secrets and variables > Actions > New repository secret`

필수/선택 Secret:

- `TOSS_CLIENT_ID`
- `TOSS_CLIENT_SECRET`
- `TOSS_ACCOUNT_SEQ`
- `TOSS_BASE_URL`
- `TOSS_HOLDINGS_URL` (실제 보유종목 endpoint 전체 URL 또는 base-relative URL)
- `TOSS_QUOTE_URL` (필요 시 현재가 endpoint)
- `KRX_AUTH_KEY`

토스 endpoint는 임의로 추정하지 않습니다. 현재 사용 중인 정상 동작 Toss API endpoint를 `TOSS_HOLDINGS_URL` 등에 넣어 연결합니다.

## GitHub Pages

Repository > Settings > Pages > Source에서 **GitHub Actions**를 선택합니다.

## 데이터 갱신

`.github/workflows/update-data.yml`이 예약 실행 또는 수동 실행으로 `scripts/fetch_data.py`를 호출해 `data/latest.json`을 갱신합니다.
