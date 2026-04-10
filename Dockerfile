FROM python:3.11-slim

# 기본 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 종속성 파일 복사 및 설치
# jira_cli, ai_chat, 그리고 jiia의 자체 requirements 모두 설치될 수 있도록 구성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 스크립트 실행 권한
RUN chmod +x jiia_main.py

# 환경변수로 외부 설정 접근 가능
ENV PYTHONUNBUFFERED=1

# 데몬으로 폴링을 시작하도록 기본 명령 설정
CMD ["python", "jiia_main.py", "--config", "config.yaml"]
