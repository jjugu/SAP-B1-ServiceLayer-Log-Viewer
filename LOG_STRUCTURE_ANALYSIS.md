# SAP B1 ServiceLayer HTTP Dump Log 구조 분석

> 이 문서는 로그 뷰어 프로그램 개발 및 유지보수 시 참고용으로 작성되었습니다.

---

## 1. 파일 개요

| 항목 | 값 |
|------|---|
| 파일명 패턴 | `dumphttp.log_YYYY_MM_DD` |
| 파일 크기 | 평일 95~213MB, 주말 23MB |
| 인코딩 | UTF-8 (한글 포함) |
| 줄바꿈 | Unix LF (`\n`), 일부 JSON body 내 Windows CRLF (`\r\n`) 혼재 |
| 서버 | Apache/2.4.54 (Unix), `hnphhana.hanaph.co.kr:50000` |
| SAP B1 버전 | 1000190 |

---

## 2. 로그 엔트리 구조

### 2.1 기본 형식

```
[요일 월 일 시:분:초 연도] [클라이언트IP] [pid=프로세스ID] [Request|Response] "HTTP메서드 URL HTTP/1.1"
헤더1:값1
헤더2:값2
...
(빈 줄 1개)
Body (JSON 등)
(빈 줄 2개 = 다음 엔트리 구분)
```

### 2.2 파싱 핵심 규칙

| 규칙 | 설명 |
|------|------|
| **엔트리 시작** | `[` 로 시작하는 줄 중 `[Request]` 또는 `[Response]` 포함 |
| **헤더/바디 구분** | 빈 줄 1개 |
| **엔트리 간 구분** | 빈 줄 2개 (연속) |
| **Request/Response 매칭** | 동일 PID 기준, 가장 최근 미매칭 Request에 Response 연결 |

### 2.3 타임스탬프 형식

```
[Sat Apr 11 00:00:04 2026]
 ^^^  ^^^  ^^ ^^^^^^^^ ^^^^
 요일  월  일   시간    연도
```
- 서버 로컬 시간 (KST, UTC+9)
- Python 파싱: `%a %b %d %H:%M:%S %Y`

---

## 3. HTTP 메서드 (3종)

| 메서드 | 용도 | 일일 빈도 |
|--------|------|----------|
| **POST** | 로그인, 엔티티 생성, 서비스 호출 | 6,000~6,800 |
| **PATCH** | 엔티티 수정 (Orders, BusinessPartners 등) | 200~1,000 |
| **GET** | 데이터 조회 (sml.svc 뷰) | 0~200 |

> PUT, DELETE는 사용되지 않음

---

## 4. API 엔드포인트 목록

### 4.1 핵심 비즈니스 엔드포인트

| 엔드포인트 | 메서드 | 설명 | 일일 빈도 |
|-----------|--------|------|----------|
| `/b1s/v1/Invoices` | POST | 매출 송장 생성 | ~670 |
| `/b1s/v1/Orders` | POST | 판매 오더 생성 | ~410 |
| `/b1s/v1/Orders(KEY)` | PATCH | 판매 오더 수정 | ~430 |
| `/b1s/v1/Orders(KEY)/Cancel` | POST | 판매 오더 취소 | ~6 |
| `/b1s/v1/BusinessPartners(KEY)` | PATCH | 거래처 수정 | ~190 |
| `/b1s/v1/StockTransfers` | POST | 재고 이전 | ~57 |
| `/b1s/v1/InventoryGenExits` | POST | 재고 출고 | ~19 |
| `/b1s/v1/InventoryGenEntries` | POST | 재고 입고 | ~3 |
| `/b1s/v1/PurchaseDeliveryNotes` | POST | 구매 입고 | ~9 |
| `/b1s/v1/PurchaseRequests` | POST | 구매 요청 생성 | ~2 |
| `/b1s/v1/PurchaseRequests(KEY)` | POST | 구매 요청 수정 | ~6 |
| `/b1s/v1/PurchaseRequests(KEY)/Close` | POST | 구매 요청 마감 | ~1 |
| `/b1s/v1/ReturnRequest` | POST | 반품 요청 | ~1 |
| `/b1s/v1/JournalEntries` | POST | 분개 전표 | ~1 |
| `/b1s/v1/Items(KEY)` | PATCH | 품목 마스터 수정 | 희소 |

### 4.2 커스텀/인터페이스 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/b1s/v1/IF_MES_OWOR` | POST | MES 작업오더 인터페이스 |
| `/b1s/v1/IF_MES_GOODS` | POST | MES 입출고 인터페이스 |
| `/b1s/v1/IF_MES_CSHIP` | POST | MES 출하 인터페이스 |
| `/b1s/v1/IF_SFA_ORRR` | POST/GET | SFA 반품 인터페이스 |
| `/b1s/v1/HNPH_3020` | POST | 커스텀 UDO |
| `/b1s/v1/HNPH_6010(KEY)` | PATCH | 커스텀 UDO 수정 |

### 4.3 시맨틱 레이어 뷰 (GET만 사용)

| 뷰 이름 | 설명 |
|---------|------|
| `sml.svc/HNPH_VW_PQT1` | 구매 견적 상세 뷰 |
| `sml.svc/HNPH_VW_REQNO` | 구매 요청 번호 뷰 |
| `sml.svc/HNPH_VW_PRQ1` | 구매 요청 상세 뷰 |
| `sml.svc/HNPH_MES_VIEW_OITM` | MES 품목 마스터 뷰 |
| `sml.svc/HNPH_VW_BUDGET_DATA` | 예산 데이터 뷰 |
| `sml.svc/HNPH_MES_VIEW_SHIP` | MES 출하 뷰 |
| `sml.svc/HNPH_VW_ITEMS` | 품목 뷰 |
| `sml.svc/HNPH_MES_VIEW_OPOR` | MES 구매오더 뷰 |
| `sml.svc/HNPH_MES_VIEW_OCRD` | MES 거래처 뷰 |
| `sml.svc/HNPH_VW_EMP` | 사원 뷰 |

### 4.4 시스템/세션 엔드포인트

| 엔드포인트 | 메서드 | 일일 빈도 |
|-----------|--------|----------|
| `/b1s/v1/Login` | POST | ~1,040 |
| `/b1s/v1/Logout` | POST | ~910 |
| `/b1s/v1/AlertService_RunAlert` | POST | ~1,360 (매 60초) |
| `/b1s/v1/$batch` | POST | ~490 (매일 01시 HR동기화) |
| `/b1s/v1/ssob1s` | POST | SSO 진입점 |
| `/b1s/v1/ssob1s/saml2/sp/acs` | POST | SAML ACS |
| `/b1s/v1/ssob1s/saml2/sp/choose_company` | POST | SSO 회사 선택 |

---

## 5. HTTP 상태 코드

| 코드 | 의미 | 발생 상황 |
|------|------|----------|
| **200 OK** | 성공 (본문 있음) | Login, GET 조회, AlertService |
| **201 Created** | 생성 성공 | POST로 엔티티 생성 시 |
| **202 Accepted** | 배치 수락 | `$batch` 요청 응답 |
| **204 No Content** | 성공 (본문 없음) | PATCH 성공, Logout |
| **302 Found** | 리다이렉트 | SSO/SAML 플로우 |
| **400 Bad Request** | 비즈니스 로직 오류 | 유효성 검증 실패 |
| **401 Unauthorized** | 인증 실패 | 세션 만료 |

---

## 6. 에러 응답 형식

### 6.1 400 Bad Request (표준 SAP B1 오류)

```json
{
   "error" : {
      "code" : -5002,
      "message" : {
         "lang" : "en-us",
         "value" : "에러 메시지 내용"
      }
   }
}
```

### 6.2 401 Unauthorized (세션 만료)

```json
{
   "error" : {
      "code" : "301",
      "message" : "Invalid session or session already timeout."
   }
}
```

> **주의:** 400 에러는 `message`가 객체(`lang`/`value`), 401은 `message`가 문자열, `code`도 문자열

### 6.3 주요 에러 코드 및 메시지

| 코드 | 메시지 패턴 | 의미 |
|------|-----------|------|
| `-5002` | Internal error / Base document closed | 내부 오류, 원천문서 마감됨 |
| `-5006` | 다양한 비즈니스 규칙 | 비즈니스 규칙 위반 |
| `-5012` | 다양한 비즈니스 규칙 | 비즈니스 규칙 위반 |
| `-1013` | 다양한 비즈니스 규칙 | 비즈니스 규칙 위반 |
| `-1116` | 다양한 비즈니스 규칙 | 비즈니스 규칙 위반 |
| `-10` | 다양한 비즈니스 규칙 | 비즈니스 규칙 위반 |
| `-1` | 커스텀 비즈니스 검증 | `[NT][HNPH]` 접두어 커스텀 검증 |
| `"301"` | Invalid session | 세션 만료 |
| `"1299"` | 다양함 | 기타 오류 |

### 6.4 자주 발생하는 에러 메시지 (한국어)

- `거래처 여신 초과 주문입니다` - 신용한도 초과
- `동일한 원천 Key로 등록된 문서가 존재합니다` - 중복 문서
- `품목 Hxxxxx은(는) 비활성 입니다` - 비활성 품목
- `사고거래처 또는 주문제한 거래처입니다` - 거래 제한
- `지급방법: 필수 입력 항목입니다` - 필수값 누락
- `Value too long in property` - 필드 길이 초과
- `Base document card and target document card do not match` - 거래처 불일치
- `Document is already closed` - 이미 마감된 문서

---

## 7. 클라이언트 식별

| IP | 역할 | User-Agent |
|----|------|------------|
| `10.10.100.100` | 메인 앱 서버 (송장, 오더, 배치) | 없음 |
| `10.10.100.101` | 알림 서비스 폴러 (60초 간격) | `Java/1.8.0_333` |
| `3.36.1.219` | MES 연동 (AWS, 재고이전/입출고) | `Apache-HttpClient/4.5.14 (Java/1.8.0_432)` |
| `210.180.238.131` | B1 웹클라이언트 (SSO, 오더수정) | `Chrome/146.0.0.0` |
| `58.229.234.3` | 구매 앱 (시맨틱 뷰 조회) | `Apache-HttpClient/4.5.14 (Java/1.8.0_411)` |
| `118.130.236.202` | MES 품목 뷰어 | - |
| `220.76.106.241` | 관리자/개발자 | `Chrome` |
| `127.0.0.1` | 로컬 헬스체크 | - |

---

## 8. 특수 패턴

### 8.1 마스킹

| 대상 | 형태 |
|------|------|
| Login 요청 Body | `****...****` (62자, 원본 길이 보존) |
| Cookie 헤더 | `Cookie:****...****` (길이 가변) |
| Set-Cookie 응답 | `Set-Cookie:****...****` (길이 가변) |

### 8.2 URL 이중 슬래시

- `10.10.100.100` 발신: `//b1s/v1/...` (이중 슬래시)
- 기타 IP 발신: `/b1s/v1/...` (단일 슬래시)
- 기능적 차이 없음, 파싱 시 정규화 필요

### 8.3 $batch 요청 형식

```
Content-Type: multipart/mixed;boundary=batch_UUID
```
- `changeset` 내부에 개별 PATCH 요청 포함
- 매일 01:00 HR 동기화용 (EmployeesInfo, SalesPersons)
- 응답: `202 Accepted`, `multipart/mixed` 본문

### 8.4 세션 플로우

```
Login (POST) → SessionId 발급 → API 호출들 → Logout (POST)
```
- SessionTimeout: 30분
- 일부 클라이언트는 `SessionId:` 헤더로 인증
- 대부분은 `Cookie:` 헤더로 인증

---

## 9. 파싱 전략 가이드

### 9.1 엔트리 분리

1. 파일을 줄 단위로 읽으며 `[` 로 시작하고 `[Request]` 또는 `[Response]`를 포함하는 줄을 엔트리 시작점으로 인식
2. 다음 엔트리 시작점까지의 모든 줄을 현재 엔트리에 포함

### 9.2 헤더 파싱 정규식

```python
# 엔트리 헤더 라인
import re
ENTRY_PATTERN = re.compile(
    r'\[(.+?)\]\s+\[(\d+\.\d+\.\d+\.\d+)\]\s+\[pid=(\d+)\]\s+'
    r'\[(Request|Response)\]\s+"(\w+)\s+(.+?)\s+HTTP/[\d.]+"'
)
# 그룹: (timestamp, ip, pid, type, method, url)
```

### 9.3 Request/Response 매칭

```python
# PID 기반 매칭 (FIFO 큐)
pending_requests = {}  # pid -> deque of Request entries
for entry in entries:
    if entry.type == 'Request':
        pending_requests.setdefault(entry.pid, deque()).append(entry)
    elif entry.type == 'Response':
        queue = pending_requests.get(entry.pid)
        if queue:
            matched_request = queue.popleft()
            yield (matched_request, entry)  # paired
```

### 9.4 노이즈 필터링 (뷰어 기본 필터)

분석 시 제외 추천:
- `AlertService_RunAlert` (60초마다 반복, 대량)
- `Login` / `Logout` (단독 조회 시 의미 낮음)
- `/balancer-manager` (Apache 헬스체크)
- SSO/SAML 플로우 (인증 인프라)

---

## 10. 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-04-16 | 초기 작성 - 5개 샘플 로그 (04/10~04/14) 기반 분석 |
