# 프로젝트 인수인계 문서 (Handoff)

> 이 문서는 다른 AI 에이전트 환경(새 Claude Code 세션, 다른 도구 등)에서 지금까지의 작업을 그대로 이어가기 위한 요약본입니다. 작성일: 2026-09-15.

---

## 1. 지금까지 만든 것 — 요약

이번 세션에서 두 개의 별도 프로젝트를 만들고 배포했습니다.

| # | 프로젝트 | 위치 | 배포 상태 |
|---|---|---|---|
| 1 | **ETNS_TODO_APP** — 간단한 할일관리 Flask 앱 (로그인 포함) | `C:\Users\etners\Desktop\ETNS_VIBE\ETNS_TODO_APP` | ✅ 배포됨: https://20260915etnsv-rho.vercel.app |
| 2 | **K-총무 WAY (K-CHONGMU_WAY)** — AI 기반 사업장 업무 동선 최적화 플랫폼 (메인 프로젝트, 현재 진행 중) | `C:\Users\etners\Desktop\ETNS_VIBE\K-CHONGMU_WAY` | ✅ 배포됨: **https://k-chongmu-way.vercel.app** |

**지금 이어서 작업해야 할 것은 대부분 2번(K-총무 WAY)입니다.**

---

## 2. 계정 / 외부 서비스 (전부 이미 연동 완료)

같은 GitHub 계정으로 두 프로젝트 다 관리 중입니다.

- **GitHub**: 계정 `Hongjunior` (seokjun999@etners.com)
  - https://github.com/Hongjunior/ETNS_TODO_APP
  - https://github.com/Hongjunior/K_CHONGMU_WAY *(주의: GitHub 저장소명은 언더스코어 `K_CHONGMU_WAY`, 로컬 폴더명은 하이픈 `K-CHONGMU_WAY` — 사용자 요청으로 로컬만 변경함, 아래 8절 참고)*
- **Vercel**: 같은 계정(GitHub 연동), 팀 슬러그 `jun-2b37`
  - 프로젝트 `20260915_etns_v` → https://20260915etnsv-rho.vercel.app
  - 프로젝트 `k-chongmu-way` → https://k-chongmu-way.vercel.app
- **Supabase**: 조직 `20260915_ETNS_S` 안에 프로젝트 2개
  - `Hongjunior's Project` (ETNS_TODO_APP용 DB)
  - `K-CHONGMU_WAY_S` (K-총무 WAY용 DB, region: ap-northeast-1)
- 모든 로그인 정보(비밀번호, PAT, DB 비밀번호)는 **채팅에 남기지 않았고 저장하지 않았습니다** — 각 서비스 대시보드에 직접 로그인해서 확인해야 합니다.

### 재사용 가능한 스킬
- `C:\Users\etners\.claude\skills\web_connector_260915\` — GitHub→Vercel→Supabase 배포 자동화 스킬. 이번 세션에서 겪은 트러블슈팅(psycopg2 vs psycopg3, Supabase 비밀번호 특수문자 금지, Vercel 도메인 추측 금지, **Vercel의 Flask 자동감지로 인한 vercel.json 충돌** 등)이 전부 기록되어 있음. 새 Flask 앱을 배포할 때 이 스킬을 그대로 다시 쓰면 됨.

---

## 3. K-총무 WAY — 원래 요청사항 (작업지시서 원문 요약)

사용자가 제공한 원 스펙: **"AI 기반 사업장 업무 동선 최적화 플랫폼"**

- 사업장(회사 캠퍼스) 내부 2D 지도 + 셔틀 정보 제공
- 사용자가 여러 업무 일정을 등록하면 **AI가 최적의 이동 순서(플랜 A/B)를 추천**
- **AI가 담당할 영역**: 자연어 일정 해석, 공지 핵심 추출, 추천 이유 설명(자연어 생성)
- **일반 알고리즘이 담당할 영역**: 이동시간 계산, 경로 탐색, 일정 순서 조합, 지각 가능성 계산 — AI에게 계산을 맡기지 않음
- 관리자/일반 사용자 권한 분리, 사업장별 데이터 격리
- MVP 우선, 실제 동작하는 기능 우선(목업 금지)

**전체 원문 스펙은 이 대화의 맨 처음 "K-총무 WAY" 요청 메시지에 있음 (14개 섹션, 매우 상세) — 이 문서에는 다 옮기지 않았으니, 원본 대화 로그를 참고할 것.**

---

## 4. 단계별 진행 상황

사용자와 합의: **한 번에 다 만들지 않고 단계별로 진행.**

### ✅ Phase 1 — 완료
- 로그인/회원가입, 사용자(user)/관리자(admin) 권한 구분
- 사업장 선택 + 사업장별 데이터 완전 격리
- DB 스키마: `worksites → buildings → floors → facilities → shuttle_routes → move_edges` (+ 미래 Phase용 `schedules`, `recommendation_logs`, `notices`, `notice_impacts` 테이블도 미리 생성해둠)
- 관리자 CRUD: 사업장/건물/층/시설/이동경로(그래프)/셔틀노선/사용자 권한
- 2D 도식화 지도 (외부 지도 API 안 씀, 순수 CSS 절대좌표 + SVG)
- 시설을 점이 아니라 **실제 크기의 사각형 블록**으로 표시 (교육장 예시 포함)

### ✅ Phase 2 — 완료
- 일정 CRUD (수동 입력, 아직 자연어 아님)
- **`routing.py`**: `move_edges` 그래프 위에서 다익스트라로 두 시설 간 실제 이동시간 계산 (순수 알고리즘, AI 아님)
  - 핵심 설계: 모든 시설은 자신이 속한 층과 이동시간 0분으로 연결된다고 취급(시설→층→층→시설 경로 성립)
  - 셔틀은 편도(순환 루프)라서 역방향 이동 시 자동으로 먼 길로 우회 계산됨 — 검증 완료
- 일정 간 "이동시간 부족" 경고 (여유시간 vs 필요 이동시간 비교)
- 셔틀 정식 시간표(`next_shuttle_departure`, `generate_timetable` in `routing.py`)

### ✅ Phase 2.5 (추가 기능, 사용자가 도중에 요청한 것들) — 완료
- 지도 배경 이미지(SVG, 사업장 전체=캠퍼스 느낌 / 층별=청사진 느낌)
- 일정 등록 시 **지도에서 건물→층→방 클릭으로 장소 선택**하는 인터랙티브 위젯 (`static/facility_picker.js`)
- 사업장 이름 변경 + 3개 추가 (삼성전자 WS센터(수원)/GA센터(용인)/GA센터(동탄), SK하이닉스 D&D(성남))
- **이트너스 브랜딩**: 실제 etners.com에서 가져온 오렌지(`#FB8520`) + 베이지 배경 + 차콜 텍스트, 실제 흰색 로고 파일 적용
- **일정 알람 팝업**: 시작 10분 전 화면에 자동 토스트 팝업 (+ 브라우저 네이티브 알림), `/schedules/api/upcoming` + `static/reminder.js`
- 셔틀 예시 데이터를 노선마다 다른 배차간격/이동시간으로 다양화
- **셔틀 전체 동선 지도** (`/map/shuttle-map`): 버스 앱처럼 건물 간 화살표로 순환 노선 전체를 지도 위에 시각화

### ❌ Phase 3 — 아직 시작 안 함 (다음에 할 일)
스펙의 진짜 핵심 기능인데 아직 미구현:
1. **자연어 일정 입력** — "내일 오전 10시에 A동 6층 회의실에서 20분 미팅" 같은 문장을 AI(Claude API)가 파싱해서 구조화된 일정으로 변환. 장소/시간이 모호하면 AI가 되묻기.
2. **AI 기반 최적 동선 추천 (플랜 A/B)** — 하루의 여러 일정을 놓고, `routing.py`의 이동시간 계산을 이용해 순열 탐색(일정 수 적으면 전체 조합 비교)으로 최적 순서를 찾고, AI가 추천 이유를 자연어로 설명. 플랜 A(최단시간)/플랜 B(여유시간 많음) 두 가지 제시.
3. **운영변경 공지 → 영향 일정 분석** (Phase 4, 스펙 6-12) — 관리자가 "A동 정문 셔틀 위치 변경" 같은 공지를 올리면 AI가 변경 대상을 추출하고 영향받는 기존 일정을 찾아줌.
4. 관리자 대시보드 통계, 일정 변경 이력, 운영정보 오류 탐지 등 나머지 스펙 항목들.

**Phase 3를 시작하려면 Anthropic API 키가 필요합니다** (사용자에게 미리 안내해뒀음, 아직 키를 안 받은 상태).

---

## 5. 기술 스택 / 아키텍처 핵심

- **Flask + SQLAlchemy Core**(ORM 아님, 원시 SQL + `text()`), 세션 기반 로그인(`werkzeug.security`)
- **듀얼 DB 백엔드**: `DATABASE_URL` 환경변수 있으면 Postgres(Supabase), 없으면 로컬 SQLite — `db.py`에서 자동 분기
- **psycopg2-binary 사용, psycopg3(`psycopg[binary]`) 금지** — Vercel 서버리스에서 psycopg3가 `OSError: Errno 16` 에러로 깨짐 (스킬 문서에 기록됨)
- **Vercel 배포**: `vercel.json`/`api/index.py` 없이 Vercel의 Flask 자동감지에만 의존 (이번 세션에서 발견한 새 이슈 — 예전엔 `vercel.json` rewrite가 필요했는데, 최근 Vercel이 `app.py`의 Flask 인스턴스를 자동으로 찾아서 내부적으로 `/flask` 경로에 마운트해버리는 바람에 수동 rewrite 설정이 충돌 → 파일 제거가 정답이었음)
- Flask **Blueprint 구조**: `blueprints/auth.py`, `worksites.py`, `admin.py`, `mapview.py`, `schedules.py`
- 정적 파일: `static/style.css`(CSS 변수로 테마 관리), `static/map.js`(지도 마커 클릭 상세패널), `static/facility_picker.js`(일정 등록 장소선택), `static/reminder.js`(알람 팝업)

---

## 6. 파일 구조 (K-CHONGMU_WAY)

```
K-CHONGMU_WAY/
  app.py                # Flask 앱 생성 + 블루프린트 등록 + init_db()/seed_demo_data()
  db.py                 # DB 엔진(Postgres/SQLite 분기), 전체 스키마 CREATE TABLE
  seed.py                # 데모 데이터 (사업장/건물/층/시설/셔틀노선/계정)
  constants.py           # 시설유형/우선순위/상태/역할 상수
  routing.py             # 다익스트라 이동시간 계산 + 셔틀 시간표 계산 (AI 아닌 순수 알고리즘)
  requirements.txt
  blueprints/
    auth.py              # 로그인/회원가입/로그아웃 + login_required/admin_required/worksite_required 데코레이터
    worksites.py          # 사업장 선택
    admin.py              # 전체 관리자 CRUD
    mapview.py            # 지도(전체/층별/검색/셔틀시간표/셔틀동선)
    schedules.py          # 일정 CRUD + 이동가능성 분석 + 알람 API
  templates/               # (auth/worksites/admin/map/schedules 하위 폴더)
  static/
    style.css, map.js, facility_picker.js, reminder.js
    img/ (site-bg.svg, floor-bg.svg, etners_logo.png)
```

---

## 7. 테스트 계정

- `admin` / `admin1234` — 관리자
- `user1` / `user1234` — 일반 사용자
- (둘 다 시드 데이터로 자동 생성됨, DB가 비어있을 때만 1회 실행)

기본 사업장 "삼성전자 WS센터 (수원)"에 건물 A동/B동/C동/식당동, 각 건물 시설, 셔틀노선 4개가 시드되어 있음.

---

## 8. 알아두면 좋은 것 (트러블슈팅 이력)

- **로컬 폴더가 "Device or resource busy"로 이름 변경이 안 될 때**: 내 PowerShell/Bash 도구 세션 자체의 현재 작업 디렉터리가 그 폴더 안에 있으면 Windows가 락을 건다. `Set-Location`으로 밖으로 나온 뒤 재시도하면 됨.
- **GitHub PAT 발급 시 `read:org` 스코프 빠뜨리기 쉬움** (별도 섹션에 있음, `admin:org` 아래).
- **Supabase DB 비밀번호에 특수문자 넣으면 연결 문자열이 깨짐** — 영문+숫자만 사용.
- **Vercel 배포 URL은 절대 추측하지 말고 대시보드에서 정확히 확인** — 프로젝트명이 정리되면서 도메인에 랜덤 접미사가 붙을 수 있음.
- 위 내용들은 전부 `web_connector_260915` 스킬 파일에도 정리되어 있음.

---

## 9. 다음 세션에서 이어갈 때 추천 순서

1. 이 문서 + `C:\Users\etners\.claude\skills\web_connector_260915\SKILL.md` 읽기
2. 로컬에서 `cd K-CHONGMU_WAY && pip install -r requirements.txt && python app.py`로 먼저 띄워서 현재 상태 확인
3. Phase 3(자연어 입력 + AI 동선 추천)부터 이어서 진행 — Anthropic API 키 필요, 사용자에게 요청
4. 코드 수정 후에는 이 세션과 동일하게: `git add -A && git commit && git push origin master` → Vercel 자동 재배포
