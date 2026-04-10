# JIIA (Jira Intelligent Issue Analyst) 설치 가이드

JIIA는 IOP 엔지니어와 SW 엔지니어 사이를 연결하는 AI 자동화 에이전트 시스템입니다. 본 시스템은 기존 `ai_chat` 모듈과 `jira_cli` 모듈을 통합하여 동작합니다.

## 디렉토리 포함 내역
이 패키지(`.zip`)에는 다음 내용이 포함되어 있습니다.
- `jiia_main.py` 및 `core/` 로직
- `ai_chat/` 의존성 패키지
- `jira_cli/` 의존성 패키지
- `config.yaml` 템플릿
- `Dockerfile` & `docker-compose.yml`

## 요구 사항
- **Docker** 및 **Docker Compose**
  - 또는 Python 3.10 이상 + `pip` (로컬 직접 실행 시)
- JIRA API 권한 토큰
- AI API 키 (Google Gemini, OpenAI, Claude 중 택 1)

---

## 1. 설정 (Config) 준비

설치 경로의 `config.yaml` 파일을 열고 다음과 같이 본인의 환경에 맞게 수정합니다.

```yaml
jira:
  base_url: "https://your-domain.atlassian.net"
  auth_type: "token"
  email: "<JIRA 봇/사용자 이메일>"
  api_token: "<JIRA API TOKEN>"
  api_version: "auto"

ai:
  provider: "gemini"     # gemini, openai, claude
  api_key: "<AI_API_KEY>"

jiia:
  polling_interval: 60
  handoff_assignee_account_id: "<SW엔지니어_ACCOUNT_ID>"
  jiia_account_id: "<JIIA_ACCOUNT_ID>" 
  labels:
    waiting: "jiia-status-waiting"
    analyzed: "jiia-status-analyzed"
```

> **참고**: `jiia_account_id`는 JIIA 시스템이 사용하는 Jira 계정의 Account ID입니다. 자신이 달았던 코멘트를 구분하기 위해 필요합니다.

---

## 2. 배포 및 실행 (Docker 방식 권장)

기본적으로 데몬 형태로 실행되어 `polling_interval` 마다 새 이슈가 있는지 점검하고 4단계 프로세스를 수행합니다.

### Docker Compose로 백그라운드 실행

```bash
# 이미지 빌드 및 컨테이너 실행
docker-compose up -d --build

# 로그 확인
docker-compose logs -f
```

---

## 3. 로컬 디버그 모드 (Dry-Run)

실제로 JIRA에 코멘트를 달거나 상태를 변경하지 않고, 로그를 통해 어떤 식으로 분석하고 행동하는지만 모니터링하고 싶을 때 유용합니다.

### 로컬 환경에서 실행하는 경우
의존성 설치:
```bash
pip install -r requirements.txt
```

Dry-run 1회 실행:
```bash
python jiia_main.py --config config.yaml --dry-run --run-once
```

폴링 데몬 기반 Dry-run 실행:
```bash
python jiia_main.py --config config.yaml --dry-run
```
