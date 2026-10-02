# Market Calendar

미국 주요 기업 실적 + 거시지표 발표 일정을 하나의 `.ics` 피드로 만들어
캘린더 앱이 구독(subscribe)하도록 하는 자동화.

GitHub Actions가 하루 두 번 `public/market.ics`를 새로 만들어 커밋하고, GitHub Pages가 공개 주소로 내보낸다.

```
https://imkim1219.github.io/market-calendar/public/market.ics
```

네이버 캘린더가 이 주소를 "URL로 구독하기"로 받는다 (2026-10-02부터).

## 구조
- `build_ics.py` — 데이터 수집 → `public/market.ics` 생성 (외부 패키지 없음, 표준 라이브러리만)
- `config.json` — 관심 종목·지표 목록, 수집 기간
- `.github/workflows/build.yml` — 매일 06:10 / 18:10 KST에 생성·커밋 (`workflow_dispatch`로 수동 실행 가능)
- `public/` — Pages로 공개되는 결과물 (`.env`는 여기 없음)
- `.env` — 로컬 실행용 `FRED_API_KEY` (git에 올리지 말 것). Actions는 저장소 Secret `FRED_API_KEY`를 쓴다
- `run.sh` — 로컬 실행 진입점 (예전 launchd용, 지금은 수동 시험용)

## 데이터 소스
| 항목 | 소스 | API 키 |
|---|---|---|
| 기업 실적 | Nasdaq earnings calendar | 불필요 |
| CPI·PPI·고용·PCE·GDP·소매판매·JOLTS·미시간대 | FRED release calendar | 무료 키 필요 |
| FOMC | federalreserve.gov calendar.json | 불필요 |

## 동작
- 매일 06:10 / 18:10 KST에 Actions가 재생성. 바뀐 게 있을 때만 `github-actions[bot]`이 커밋한다
- GitHub 예약 실행은 몇 시간씩 늦을 수 있다 (06:10 예약이 09:43에 돈 적 있음, 2026-10-02)
- 실적 UID는 `종목+날짜` 해시 → 일정이 바뀌면 새 이벤트, 같으면 중복 없음
- 시간은 ET 기준으로 계산해 UTC로 기록 → 캘린더 앱이 KST로 자동 변환
- `장전`=07:00 ET, `장후`=16:15 ET, `시간미정`=09:00 ET
- 모든 일정에 `config.json`의 `category`("미국 경제")를 `CATEGORIES`로 넣는다. 네이버 구독 일정은 읽기 전용이라
  범주를 직접 고를 수 없어서 넣어 본 것 (2026-10-02). 네이버가 이 값을 범주로 읽는지는 확인 전

## 수동 실행 / 확인
```
gh workflow run build.yml --repo imkim1219/market-calendar
gh run list --repo imkim1219/market-calendar --limit 3
curl -s https://imkim1219.github.io/market-calendar/public/market.ics | grep -c BEGIN:VEVENT
```

로컬에서 시험하려면 `./run.sh && tail -5 build.log`. 이때 바뀐 `public/market.ics`는 커밋하지 않는다
(봇 커밋과 충돌한다). 버리려면 `git checkout -- public/market.ics`.

## 종목 바꾸기
`config.json`의 `watchlist`를 고치고 `git pull --rebase` 후 push → 위의 `gh workflow run`으로 바로 반영하거나
다음 예약 실행을 기다린다. 구독한 캘린더는 다음 새로고침에 반영된다.

## 처음 설정 (기록용, 이미 끝남)
1. FRED 키 발급 → https://fredaccount.stlouisfed.org/apikey
2. GitHub에 **public** 리포 생성 (Pages가 공개 리포에서만 무료)
3. Settings > Secrets and variables > Actions 에 `FRED_API_KEY` 등록
4. Settings > Pages > Source = `main` 브랜치 `/ (root)`
5. 캘린더 앱에서 위 공개 주소를 구독

`.gitignore`가 `.env`와 `cache/`를 제외하므로 FRED 키는 커밋되지 않는다.

## 예전 Mac 생성기 (꺼짐)
처음에는 Mac의 launchd가 매일 07:10 / 19:10에 `run.sh`로 생성하고(`com.peter.marketcal.build`),
`http://127.0.0.1:8912/market.ics`로 내보냈다(`com.peter.marketcal.serve`). 이 주소는 Mac 밖(아이폰·네이버)에서
닿지 않아서 GitHub Pages로 옮겼고, 2026-10-02에 두 작업을 `bootout` + `disable`로 껐다.
plist는 `~/Library/LaunchAgents/`에 남아 있다.

### 알려진 위험
Nasdaq API가 데이터센터 IP를 봇으로 차단할 수 있음. Actions 로그에서 실적이 0건이면 차단된 것이다
(2026-10-02 기준 15건 정상). 그 경우 Mac 생성기를 다시 켜고 `run.sh` 끝에 `git push`를 붙여 결과만 리포에
올리는 방식으로 전환한다 (대신 Mac이 켜져 있어야 함).

```
launchctl enable gui/$(id -u)/com.peter.marketcal.build
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.peter.marketcal.build.plist
```
