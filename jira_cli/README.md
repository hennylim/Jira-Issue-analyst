# JIRA CLI 관리 툴

Python 기반 JIRA 관리 CLI 툴.
JIRA REST API v2/v3 자동 감지, 외부 config 파일, 로그 저장, 프로젝트 간 이슈 복사 지원.

---

## 📁 프로젝트 구조

```
jira_cli/
├── jira_cli.py              ← CLI 진입점 (argparse 기반)
├── config.yaml              ← 외부 설정 파일 (JIRA URL, 인증, 기본값, 로그 등)
├── requirements.txt
├── logs/                    ← 날짜별 로그 파일 자동 생성
├── jira/
│   ├── client.py            ← ★ 재사용 가능한 JiraClient 클래스
│   ├── api_handler.py       ← API v2/v3 자동 감지 및 요청 핸들러
│   └── models.py            ← 데이터 모델 (JiraIssue, JiraComment, CopyResult 등)
├── commands/
│   ├── issue.py             ← 이슈 조회/생성/수정/복사 명령어
│   ├── comment.py           ← 댓글 추가/조회/수정/삭제 명령어
│   └── status.py            ← 상태 변경/담당자/레이블 명령어
└── utils/
    ├── config_loader.py     ← YAML 설정 로더 (환경변수 오버라이드 지원)
    └── logger.py            ← 파일 로테이션 + 콘솔 컬러 로거
```

---

## ⚙️ 설치

```bash
pip install -r requirements.txt
```

---

## 🔧 설정

`config.yaml` 파일을 열어 아래 항목을 수정합니다.

```yaml
jira:
  base_url:    "https://your-domain.atlassian.net"
  auth_type:   "token"          # token | pat | basic
  email:       "you@example.com"
  api_token:   "your_api_token"
  api_version: "auto"           # auto | 2 | 3
  timeout:     30
  verify_ssl:  true
  max_retries: 3

defaults:
  project_key: "MYPROJECT"     # 기본 프로젝트 키 (-p 생략 시 사용)
  issue_type:  "Task"
  priority:    "Medium"
  max_results: 50

transitions:                   # 상태 별칭 (status change 명령에서 사용)
  todo:        ["To Do", "Open", "Backlog"]
  in_progress: ["In Progress", "Start Progress", "진행 중"]
  in_review:   ["In Review", "Code Review"]
  done:        ["Done", "Resolve Issue", "완료"]
```

### 환경변수 오버라이드 (보안 권장)

config.yaml 에 API 토큰을 직접 기입하는 대신 환경변수를 사용할 수 있습니다.

```bash
# Windows PowerShell
$env:JIRA_BASE_URL  = "https://your-domain.atlassian.net"
$env:JIRA_EMAIL     = "you@example.com"
$env:JIRA_API_TOKEN = "your_token"

# macOS / Linux
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="your_token"
```

| 환경변수 | 대응 config 키 |
|---|---|
| `JIRA_BASE_URL` | `jira.base_url` |
| `JIRA_EMAIL` | `jira.email` |
| `JIRA_API_TOKEN` | `jira.api_token` |
| `JIRA_PAT` | `jira.pat` |
| `JIRA_API_VERSION` | `jira.api_version` |

---

## 🚀 전체 명령어 목록

```
jira_cli
├── ping                            JIRA 서버 연결 확인
├── issue
│   ├── get      <KEY>              이슈 상세 조회
│   ├── search   [JQL]              이슈 검색 (JQL 또는 조건 옵션)
│   ├── create                      이슈 생성
│   ├── update   <KEY>              이슈 필드 수정
│   └── copy     <KEY> <PROJECT>    이슈를 다른 프로젝트로 복사
├── comment
│   ├── add      <KEY> <TEXT>       댓글 추가
│   ├── list     <KEY>              댓글 목록 조회
│   ├── update   <KEY> <ID> <TEXT>  댓글 수정
│   └── delete   <KEY> <ID>         댓글 삭제
├── status
│   ├── change      <KEY> <STATUS>  상태 변경
│   ├── transitions <KEY>           가능한 전환 목록 조회
│   └── assign      <KEY>           담당자 변경
└── label
    ├── add    <KEY> <LABEL>        레이블 추가
    └── remove <KEY> <LABEL>        레이블 제거
```

---

## 📖 사용법 상세

### 공통 옵션

```bash
python jira_cli.py -c /path/to/config.yaml <명령어>   # 설정 파일 지정
python jira_cli.py --debug <명령어>                   # DEBUG 로그 출력
```

> `-f / --format` 옵션은 출력이 있는 서브커맨드 뒤에 직접 붙입니다.
> 예) `issue get PROJ-123 -f json`  (전역에 붙이는 것도 동일하게 동작)

---

### 🔌 연결 확인

```bash
python jira_cli.py ping
```

```
✅ 연결 성공!
   서버  : Jira
   버전  : 1001.0.0-SNAPSHOT
   배포  : Cloud
   URL   : https://your-domain.atlassian.net
```

---

### 📄 이슈 조회

```bash
python jira_cli.py issue get PROJ-123
python jira_cli.py issue get PROJ-123 -f json
```

---

### 🔍 이슈 검색

```bash
# JQL 직접 입력
python jira_cli.py issue search "project = SI AND status = Open ORDER BY created DESC"

# 담당자 없는 미할당 이슈
python jira_cli.py issue search "project = SI AND assignee IN (empty) AND status = Open"

# 조건 옵션 조합
python jira_cli.py issue search -p SI --status "In Progress" -a currentUser --max 20

# JSON 출력
python jira_cli.py issue search -p SI -f json
```

---

### ➕ 이슈 생성

```bash
# 기본 생성
python jira_cli.py issue create -p SI -s "새 기능 개발" -t Story --priority High

# 설명 + 레이블 + 기한 포함
python jira_cli.py issue create \
  -p SI \
  -s "버그 수정" \
  -d "로그인 오류 발생" \
  --labels bug,urgent \
  --due-date 2026-04-30
```

| 옵션 | 설명 |
|---|---|
| `-p, --project` | 프로젝트 키 (미지정 시 config 기본값 사용) |
| `-s, --summary` | 이슈 제목 **(필수)** |
| `-t, --type` | 이슈 유형 (Task / Story / Bug / Epic 등) |
| `-d, --description` | 설명 |
| `--priority` | 우선순위 (Highest / High / Medium / Low / Lowest) |
| `--labels` | 레이블 (쉼표 구분, 예: `bug,urgent`) |
| `--due-date` | 기한 (YYYY-MM-DD) |

---

### ✏️ 이슈 수정

```bash
python jira_cli.py issue update PROJ-123 -s "수정된 제목"
python jira_cli.py issue update PROJ-123 --priority Critical --labels hotfix
python jira_cli.py issue update PROJ-123 --due-date 2026-05-31
```

---

### 📋 이슈 복사 (프로젝트 간)

다른 프로젝트로 이슈를 복사합니다.  
기본적으로 원본 이슈에 `Clones` 링크가 자동 생성됩니다.

```bash
# 기본 복사: SI-100 → OPS 프로젝트
python jira_cli.py issue copy SI-100 OPS

# 제목 앞뒤에 텍스트 추가
python jira_cli.py issue copy SI-100 OPS --summary-prefix "[복사] "
python jira_cli.py issue copy SI-100 OPS --summary-suffix " (OPS용)"

# 제목 완전 교체
python jira_cli.py issue copy SI-100 OPS --summary "완전히 새로운 제목"

# 유형 / 우선순위 / 기한 변경하여 복사
python jira_cli.py issue copy SI-100 OPS -t Bug --priority High --due-date 2026-06-30

# 댓글 함께 복사
python jira_cli.py issue copy SI-100 OPS --copy-comments

# 서브태스크 재귀 복사 + 댓글 복사
python jira_cli.py issue copy SI-100 OPS --copy-comments --copy-subtasks

# 레이블·설명 제외, 링크 생성 안 함
python jira_cli.py issue copy SI-100 OPS --no-labels --no-description --no-link

# JSON 출력
python jira_cli.py issue copy SI-100 OPS -f json
```

**`issue copy` 옵션 전체 목록:**

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `key` | 원본 이슈 키 **(필수)** | — |
| `target_project` | 대상 프로젝트 키 **(필수)** | — |
| `--summary` | 새 제목으로 교체 | 원본 제목 그대로 |
| `--summary-prefix` | 제목 앞에 추가 (예: `[복사] `) | `""` |
| `--summary-suffix` | 제목 뒤에 추가 (예: ` (복사본)`) | `""` |
| `-t, --type` | 이슈 유형 변경 | 원본과 동일 |
| `--priority` | 우선순위 변경 | 원본과 동일 |
| `--assignee` | 담당자 account_id 변경 | 원본과 동일 |
| `--due-date` | 기한 변경 (YYYY-MM-DD) | 원본과 동일 |
| `--copy-comments` | 댓글 복사 | False (복사 안 함) |
| `--copy-subtasks` | 서브태스크 재귀 복사 | False (복사 안 함) |
| `--no-labels` | 레이블 복사 안 함 | 복사함 |
| `--no-description` | 설명 복사 안 함 | 복사함 |
| `--no-link` | 원본에 Clones 링크 생성 안 함 | 생성함 |
| `-f, --format` | 출력 형식 (table / json) | table |

---

### 💬 댓글 관리

```bash
# 댓글 추가
python jira_cli.py comment add PROJ-123 "작업을 시작했습니다."

# 댓글 목록 조회
python jira_cli.py comment list PROJ-123
python jira_cli.py comment list PROJ-123 -f json

# 댓글 수정
python jira_cli.py comment update PROJ-123 10001 "수정된 댓글 내용"

# 댓글 삭제 (확인 프롬프트)
python jira_cli.py comment delete PROJ-123 10001

# 댓글 삭제 (확인 없이)
python jira_cli.py comment delete PROJ-123 10001 -y
```

---

### 🔄 상태 변경

```bash
# 상태 이름으로 직접 변경
python jira_cli.py status change PROJ-123 "In Progress"

# 상태 변경 + 댓글 동시 추가
python jira_cli.py status change PROJ-123 "Done" -c "배포 완료"

# config.yaml transitions 별칭 사용
python jira_cli.py status change PROJ-123 in_review
python jira_cli.py status change PROJ-123 done

# 가능한 전환 목록 확인 (변경 전 확인용)
python jira_cli.py status transitions PROJ-123
python jira_cli.py status transitions PROJ-123 -f json
```

---

### 👤 담당자 변경

```bash
# 담당자 지정
python jira_cli.py status assign PROJ-123 --account-id "712020:abc123"

# 담당자 해제
python jira_cli.py status assign PROJ-123
```

---

### 🏷️ 레이블 관리

```bash
python jira_cli.py label add    PROJ-123 bug
python jira_cli.py label remove PROJ-123 bug
```

---

## 🔁 다른 스크립트에서 JiraClient 재사용

`JiraClient` 클래스는 독립적으로 import하여 자동화 스크립트에서 바로 사용할 수 있습니다.

```python
from jira.client import JiraClient
from utils.config_loader import ConfigLoader

# 방법 1: config 파일로 초기화
cfg    = ConfigLoader("config.yaml")
client = JiraClient.from_config(cfg)

# 방법 2: 직접 파라미터로 초기화
client = JiraClient(
    base_url  = "https://your-domain.atlassian.net",
    auth_type = "token",
    email     = "you@example.com",
    api_token = "your_token",
)

# ── 이슈 ─────────────────────────────────────────────
issue = client.get_issue("PROJ-123")
print(issue.summary, issue.status, issue.due_date)

issues = client.search_issues("project = SI AND assignee IN (empty)")
for i in issues:
    print(i.key, i.summary)

new_issue = client.create_issue(
    project_key = "OPS",
    summary     = "자동 생성 이슈",
    issue_type  = "Task",
    due_date    = "2026-06-30",
    labels      = ["auto", "script"],
)

# ── 댓글 ─────────────────────────────────────────────
client.add_comment("PROJ-123", "자동화 스크립트에서 추가된 댓글")
comments = client.get_comments("PROJ-123")

# ── 상태 변경 ─────────────────────────────────────────
client.transition_issue("PROJ-123", "In Progress")

# ── 이슈 복사 ─────────────────────────────────────────
result = client.copy_issue(
    source_key      = "SI-100",
    target_project  = "OPS",
    summary_prefix  = "[복사] ",
    copy_comments   = True,
    copy_subtasks   = True,
    override_due_date = "2026-07-01",
)
print(f"{result.source.key} → {result.new_issue.key}")
print(f"복사된 댓글: {result.copied_comments}개")
print(f"복사된 서브태스크: {result.copied_subtasks}")
```

---

## 📋 로그

`logs/jira_cli_YYYYMMDD.log` 에 날짜별로 자동 저장됩니다.
최대 파일 크기(10MB) 초과 시 자동 롤오버, 최대 7개 파일 보관.

```
2026-03-18 12:14:47 | INFO     | jira_cli.api    | JIRA API version: v3
2026-03-18 12:14:47 | INFO     | jira_cli.client | JiraClient ready [https://your-domain.atlassian.net/]
2026-03-18 12:14:48 | INFO     | jira_cli.client | COPY issue SI-100 → project [OPS]
2026-03-18 12:14:49 | INFO     | jira_cli.client |   Created: OPS-55 '[복사] 이슈 제목'
2026-03-18 12:14:49 | INFO     | jira_cli.client |   Linked: OPS-55 Clones SI-100
```

`config.yaml` 의 `logging` 섹션에서 레벨, 경로, 파일 크기 등을 조정할 수 있습니다.

---

## 🔐 API 버전 자동 감지

서버 접속 시 `serverInfo` API를 호출하여 배포 유형을 자동으로 확인합니다.

| 환경 | 감지 조건 | API 버전 | Search 엔드포인트 |
|---|---|---|---|
| Atlassian Cloud | `deploymentType = Cloud` | v3 (ADF body) | `POST /rest/api/3/search/jql` |
| Server / Data Center | `deploymentType = Server` | v2 (plain text) | `POST /rest/api/2/search` |
| 감지 실패 | fallback | v2 | `POST /rest/api/2/search` |

`config.yaml` 에서 `api_version: "2"` 또는 `"3"` 으로 강제 지정도 가능합니다.

> **Cloud 전용:** Atlassian은 2024년부터 `POST /rest/api/3/search` 를 폐기하고
> `POST /rest/api/3/search/jql` 로 교체했습니다 (CHANGE-2046).
> 본 도구는 v3 감지 시 자동으로 신규 엔드포인트를 사용합니다.
