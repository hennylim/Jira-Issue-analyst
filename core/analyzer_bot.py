import json
import logging
from typing import Dict, Any, Tuple
from ai_chat import create_ai

logger = logging.getLogger(__name__)

# 프롬프트 정의
INITIAL_SCAN_PROMPT = """\
당신은 'JIIA(Jira Intelligent Issue Analyst)' 입니다. SW 엔지니어와 외부 필드(IOP) 엔지니어 사이를 조율하는 역할을 합니다.
다음 제출된 이슈 제목과 설명을 읽고, 내부 SW 엔지니어가 이슈를 파악하고 원인을 분석하기에 충분한 데이터(로그, 재현경로, 스크린샷 텍스트, 구성 정보 등)가 있는지 판단하세요.
만약 정보가 부족하다면, IOP 엔지니어에게 구체적으로 어떤 추가 정보를 요청할지 질문을 작성하세요.

출력은 반드시 유효한 JSON 형식이어야 합니다. 다른 말은 절대 추가하지 마세요.
{
  "status": "SUFFICIENT" 또는 "INSUFFICIENT",
  "reason": "왜 그렇게 판단했는지 짧은 이유",
  "questions_for_iop": "INSUFFICIENT일 경우, IOP 엔지니어에게 물어볼 친절한 질문 내용(마크다운 코멘트 형식). SUFFICIENT일 경우 빈 문자열."
}
"""

COMPREHENSIVE_ANALYSIS_PROMPT = """\
당신은 'JIIA' 시스템의 수석 분석가입니다. 이슈 보고와 이후 코멘트를 통한 모든 논의 데이터가 충분히 수집되었습니다.
아래에 제공된 [티켓 데이터 및 대화 내역]을 기반으로 다음 내용을 포함한 마크다운 문서를 작성하세요:
1. **문제 요약 (Issue Summary)**
2. **추정되는 근본 원인 (Estimated Root Cause)**
3. **관련 로그 및 증상 분석 (Logs & Symptoms Analysis)**
4. **SW 엔지니어를 위한 추천 수정 방향 (Recommended Fix/Action for SW Engineer)**

출력 형식은 마크다운 그대로여야 합니다. 이 결과는 PDF로 생성되어 JIRA에 첨부될 것입니다.
"""

class AnalyzerBot:
    def __init__(self, config: dict):
        ai_cfg = config.get("ai", {})
        self.provider = ai_cfg.get("provider", "gemini")
        # create_ai에 api_keys.json 경로를 넘기는 대신, api_key를 바로 넘기고 싶지만 
        # ai_chat 모듈의 create_ai는 기본적으로 config_path를 읽습니다.
        # 따라서 환경설정의 api_key를 직접 사용할 수 있도록 로직을 살짝 우회하거나, 
        # JIIA 시작 시 config.yaml의 값을 기반으로 임시 api_keys.json을 만들 수 있습니다.
        # 하지만 기존 ai_factory.py를 보면 `provider_lower not in keys` 와 같이 체크합니다.
        # 여기서는 워크어라운드로 `create_ai`의 설계를 존중하기 위해 
        # 임시 json 파일을 생성하거나 직접 할당하는 방식 중 선택합니다.
        
        self.ai_client = None
        self._init_client(self.provider, ai_cfg.get("model", ""), ai_cfg.get("api_key", ""))

    def _init_client(self, provider: str, model: str, api_key: str):
        # ai_factory 가 api_keys.json을 강제하므로 파일 생성
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_key_file = os.path.join(temp_dir, "jiia_api_keys.json")
        with open(temp_key_file, "w") as f:
            json.dump({provider.lower(): {"api_key": api_key}}, f)
            
        from ai_chat import create_ai
        self.ai_client = create_ai(
            provider=provider, 
            config_path=temp_key_file, 
            model=model if model else None
        )

    def initial_scan(self, issue_summary: str, issue_description: str) -> Tuple[str, str, str]:
        """
        초기 스캔을 수행합니다.
        반환: (상태, 이유, IOP질문)
        상태는 "SUFFICIENT" 또는 "INSUFFICIENT" 입니다.
        """
        user_msg = f"이슈 제목: {issue_summary}\n\n이슈 설명:\n{issue_description}"
        try:
            # system prompt 설정 기능이 베이스에 있을 수 있으나, chat() 메시지에 직접 합쳐 보냄
            full_prompt = f"{INITIAL_SCAN_PROMPT}\n\n[이슈 데이터]\n{user_msg}"
            response = self.ai_client.chat(full_prompt)
            # 마크다운 코드 블록(```json ... ```) 제거 로직
            answer = response.answer.strip()
            if answer.startswith("```json"):
                answer = answer[7:]
            if answer.startswith("```"):
                answer = answer[3:]
            if answer.endswith("```"):
                answer = answer[:-3]
                
            data = json.loads(answer.strip())
            return data.get("status", "INSUFFICIENT"), data.get("reason", ""), data.get("questions_for_iop", "")
        except Exception as e:
            logger.error(f"초기 스캔 AI 분석 실패: {e}")
            return "INSUFFICIENT", "AI 분석 오류", "현재 이슈를 분석하는 중 오류가 발생했습니다. 로그를 다시 확인해주시겠습니까?"

    def comprehensive_analysis(self, full_context: str) -> str:
        """
        모든 데이터를 기반으로 최종 PDF용 분석 문서를 생성합니다.
        """
        full_prompt = f"{COMPREHENSIVE_ANALYSIS_PROMPT}\n\n[티켓 데이터 및 대화 내역]\n{full_context}"
        try:
            response = self.ai_client.chat(full_prompt)
            return response.answer
        except Exception as e:
            logger.error(f"종합 분석 AI 분석 실패: {e}")
            return f"분석 중 오류가 발생했습니다.\n에러: {str(e)}"
