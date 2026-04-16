# SAP B1 ServiceLayer Log Viewer

SAP Business One ServiceLayer의 HTTP dump 로그(`dumphttp.log`)를 분석하는 데스크톱 애플리케이션입니다.

## 주요 기능

- **로그 파싱** - 대용량 로그 파일(200MB+)을 수 초 만에 분석
- **Request/Response 쌍 매칭** - PID 기반으로 요청과 응답을 자동 매칭
- **필터링** - 시간대, 엔드포인트, HTTP 메서드, 상태 코드, 클라이언트 IP
- **본문 검색** - CardCode, 품목코드, 에러 메시지 등 JSON body 내 텍스트 검색
- **에러 추적** - 400/401 에러만 모아보기, 에러 코드/메시지 바로 확인
- **JSON 뷰어** - Request/Response를 나란히 비교, 구문 강조 표시
- **노이즈 필터** - Login/Logout/Alert 등 반복 트래픽 자동 숨기기
- **컬럼 리사이즈** - 테이블 컬럼 폭 드래그 조절

## 스크린샷

```
┌─────────────────────────────────────────────────────────┐
│  SL Log Viewer  [SAP B1]          [로그 파일 열기] [종료]│
├──────────┬──────────────────────────────────────────────┤
│ 필터      │  # 시간     메서드  엔드포인트    상태  에러  │
│ 시간대    │  1 09:00:05 POST  /Invoices    400  ...   │
│ 엔드포인트│  2 09:00:22 POST  /Orders      201        │
│ 메서드    │  3 09:01:17 PATCH /Orders(KEY) 204        │
│ 상태코드  ├──────────────────────────────────────────────┤
│ IP       │  Request              │  Response            │
│ 본문검색  │  POST /b1s/v1/Orders │  201 Created         │
│          │  { "CardCode": ...}  │  { "DocEntry": ...}  │
└──────────┴──────────────────────────────────────────────┘
```

## 사용법

### exe 실행 (권장)

1. [Releases](../../releases)에서 `SL_Log_Viewer.exe` 다운로드
2. 더블클릭 - 브라우저에 UI 자동 오픈
3. "로그 파일 열기" → `dumphttp.log` 파일 선택
4. 자동 파싱 후 조회/검색

> 별도 설치 불필요. 브라우저 탭을 닫으면 앱이 자동 종료됩니다.

### 소스에서 실행

```bash
pip install flask
cd app
python main.py
```

### exe 빌드

```bash
pip install flask pyinstaller
python -m PyInstaller build.spec --noconfirm
# dist/SL_Log_Viewer.exe 생성
```

## 프로젝트 구조

```
├── app/
│   ├── main.py              # 진입점 (Flask 서버 + 브라우저 실행)
│   ├── parser.py            # 로그 파서 (→ SQLite 임시 DB)
│   ├── server.py            # Flask API 서버
│   ├── templates/
│   │   └── index.html       # 메인 UI
│   └── static/
│       ├── css/style.css    # Octo Code 다크 테마
│       └── js/app.js        # 프론트엔드 로직
├── build.spec               # PyInstaller 빌드 설정
├── requirements.txt          # Python 의존성
├── DESIGN.md                # UI 디자인 시스템 (Octo Code)
└── LOG_STRUCTURE_ANALYSIS.md # 로그 구조 분석 문서
```

## 지원하는 로그 형식

SAP B1 ServiceLayer의 `dumphttp.log` 파일:

```
[Sat Apr 11 00:00:05 2026] [10.10.100.100] [pid=22388] [Request] "POST //b1s/v1/Invoices HTTP/1.1"
Accept:application/json
Content-Type:application/json;charset=utf8
...

{
  "CardCode": "11000230",
  "DocumentLines": [...]
}
```

### 지원 엔드포인트

Invoices, Orders, BusinessPartners, StockTransfers, PurchaseDeliveryNotes, InventoryGenExits, JournalEntries, 커스텀 UDO, sml.svc 뷰 등 ServiceLayer 전체 엔드포인트

### 지원 HTTP 메서드

POST, PATCH, GET

## 기술 스택

| 구성 요소 | 기술 |
|----------|------|
| 백엔드 | Python + Flask |
| 프론트엔드 | HTML/CSS/JS (Vanilla) |
| DB | SQLite (임시, 앱 종료 시 삭제) |
| 디자인 | Octo Code (다크 테마) |
| 패키징 | PyInstaller (단일 exe) |
| 폰트 | Inter (UI) + JetBrains Mono (코드) |

## 검색 예시

| 검색어 | 용도 |
|--------|------|
| `11000230` | 특정 거래처(CardCode) 관련 전체 API 호출 |
| `H20001` | 특정 품목코드 포함 건 |
| `여신 초과` | 신용한도 초과 에러 |
| `비활성` | 비활성 품목 에러 |
| `HPRD` | 특정 창고코드 관련 건 |

## 제작

**km.joo** (jkm3383@gmail.com)

## 라이선스

MIT
