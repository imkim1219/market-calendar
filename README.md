# Market Calendar

미국 주요 기업 실적 + 거시지표 발표 일정을 하나의 `.ics` 피드로 만들어
캘린더 앱이 구독(subscribe)하도록 하는 자동화.

## 구조
- `build_ics.py` — 데이터 수집 → `public/market.ics` 생성 (외부 패키지 없음, 표준 라이브러리만)
- `config.json` — 관심 종목·지표 목록, 수집 기간
- `.env` — `FRED_API_KEY` (git에 올리지 말 것)
- `run.sh` — launchd가 호출하는 진입점
- `public/` — 로컬 HTTP로 노출되는 유일한 디렉터리 (`.env`는 여기 없음)

## 데이터 소스
| 항목 | 소스 | API 키 |
|---|---|---|
| 기업 실적 | Nasdaq earnings calendar | 불필요 |
| CPI·PPI·고용·PCE·GDP·소매판매·JOLTS·미시간대 | FRED release calendar | 무료 키 필요 |
| FOMC | federalreserve.gov calendar.json | 불필요 |

## 설치 (수동 1회)
1. FRED 키 발급 → https://fredaccount.stlouisfed.org/apikey
   `.env`의 `FRED_API_KEY=` 뒤에 붙여넣기
2. launchd 등록:
   ```
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.peter.marketcal.build.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.peter.marketcal.serve.plist
   ```
3. 캘린더 앱에서 구독 추가
   - macOS 캘린더: 파일 > 새로운 캘린더 구독 > `http://127.0.0.1:8912/market.ics`
     자동 새로고침 "매시간", 알림/첨부 "제거" 권장
   - Google 캘린더: 로컬 주소는 불가 → 아래 "외부 공개" 참고

## 동작
- 매일 07:10 / 19:10에 재생성 (`StartCalendarInterval`)
- 실적 UID는 `종목+날짜` 해시 → 일정이 바뀌면 새 이벤트, 같으면 중복 없음
- 시간은 ET 기준으로 계산해 UTC로 기록 → 캘린더 앱이 KST로 자동 변환
- `장전`=07:00 ET, `장후`=16:15 ET, `시간미정`=09:00 ET

## 수동 실행 / 확인
```
./run.sh && tail -5 build.log
grep -c BEGIN:VEVENT public/market.ics
```

## 종목 바꾸기
`config.json`의 `watchlist` 수정 후 `./run.sh`. 캘린더는 다음 새로고침에 반영.

## 외부 공개(아이폰에서도 보려면)
로컬 `127.0.0.1` 주소는 아이폰에서 도달할 수 없고, 구독을 iCloud 위치에 저장해도
Apple 서버가 URL을 대신 가져가므로 마찬가지로 실패한다. 공개 URL이 필요하다.

`.github/workflows/build.yml`이 준비돼 있음. 설정 순서:
1. GitHub에 **public** 리포 생성 (Pages가 공개 리포에서만 무료)
2. Settings > Secrets and variables > Actions 에 `FRED_API_KEY` 등록
3. push 후 Settings > Pages > Source = `main` 브랜치 `/ (root)`
4. 아이폰 캘린더에서 구독:
   `https://<사용자명>.github.io/<리포명>/public/market.ics`

`.gitignore`가 `.env`와 `cache/`를 제외하므로 FRED 키는 커밋되지 않는다.

### 알려진 위험
Nasdaq API가 데이터센터 IP를 봇으로 차단할 수 있음. Actions 로그에서 실적이 0건이면
차단된 것이고, 그 경우 생성은 Mac에서 계속하고 `run.sh` 끝에 `git push`를 붙여
결과만 리포에 올리는 방식으로 전환한다 (대신 Mac이 켜져 있어야 함).

## 제거
```
launchctl bootout gui/$(id -u)/com.peter.marketcal.build
launchctl bootout gui/$(id -u)/com.peter.marketcal.serve
```
