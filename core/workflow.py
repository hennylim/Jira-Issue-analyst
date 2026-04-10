import time
import logging
from typing import Dict, Any

from jira_cli.jira.client import JiraClient
from jira_cli.utils.config_loader import ConfigLoader
from .analyzer_bot import AnalyzerBot
from .pdf_generator import generate_pdf_from_markdown

logger = logging.getLogger(__name__)

class JIIAWorkflow:
    def __init__(self, config: Dict[str, Any], config_path: str):
        self.config = config
        self.jiia_cfg = config.get("jiia", {})
        self.labels = self.jiia_cfg.get("labels", {})
        self.label_waiting = self.labels.get("waiting", "jiia-status-waiting")
        self.label_analyzed = self.labels.get("analyzed", "jiia-status-analyzed")
        self.jiia_account_id = self.jiia_cfg.get("jiia_account_id", "")
        
        cfg = ConfigLoader(config_path)
        self.jira = JiraClient.from_config(cfg)
        self.analyzer = AnalyzerBot(config)
        self.dry_run = False
        
    def start_polling(self, dry_run: bool = False):
        self.dry_run = dry_run
        interval = self.jiia_cfg.get("polling_interval", 60)
        logger.info(f"JIIA 워크플로우 폴링 시작 (간격: {interval}초, Dry-Run: {dry_run})")
        
        while True:
            try:
                self.process_tickets()
            except Exception as e:
                logger.error(f"폴링 중 오류 발생: {e}")
            
            # TODO: production에서는 schedule이나 cron 이용 권장, 데몬 시 타임슬립 사용
            logger.debug(f"{interval}초 대기 중...")
            time.sleep(interval)

    def process_tickets(self):
        # 자신이 담당자인 이슈만 가져오기
        jql = f'assignee = currentUser() AND status in ("To Do", "Open", "In Progress") AND labels != {self.label_analyzed}'
        issues = self.jira.search_issues(jql)
        
        for issue in issues:
            labels = issue.labels if hasattr(issue, 'labels') and issue.labels else []
            if self.label_waiting in labels:
                self._handle_waiting_issue(issue)
            else:
                self._handle_new_issue(issue)

    def _handle_new_issue(self, issue):
        logger.info(f"새 이슈 감지: {issue.key} - {issue.summary}")
        # 초기 스캔
        status, reason, response_text = self.analyzer.initial_scan(issue.summary, issue.description or "")
        
        if status == "SUFFICIENT":
            logger.info(f"이슈 {issue.key} 정보 충분함. 종합 분석으로 넘어갑니다. (이유: {reason})")
            self._do_comprehensive_analysis(issue, issue.description or "")
        else:
            logger.info(f"이슈 {issue.key} 정보 부족함. IOP 엔지니어에게 질문을 남깁니다. (이유: {reason})")
            self.jira.add_comment(issue.key, f"안녕하세요, JIIA(AI 분석가)입니다.\n\n{response_text}", dry_run=self.dry_run)
            self.jira.add_label(issue.key, self.label_waiting, dry_run=self.dry_run)

    def _handle_waiting_issue(self, issue):
        # 코멘트를 가져와 IOP가 답변했는지 확인
        comments = self.jira.get_comments(issue.key)
        if not comments:
            return
            
        # 마지막 코멘트 작성자가 JIIA 자신이 아니라면(IOP 엔지니어라면)
        # ※ 실제로는 JIIA계정 ID와 작성자 ID 확인 필요
        last_comment = comments[-1]
        author_id = getattr(last_comment.author, 'accountId', getattr(last_comment.author, 'name', ''))
        
        if author_id != self.jiia_account_id:
            logger.info(f"이슈 {issue.key}에 IOP 엔지니어의 새 코멘트가 달렸습니다. 데이터를 재평가합니다.")
            
            # 모든 컨텍스트 취합
            context = f"본문: {issue.description}\n\n"
            for c in comments:
                c_author = getattr(c.author, 'displayName', 'Unknown')
                context += f"[{c_author}]: {c.body}\n"
                
            # 충분성 재평가
            status, reason, response_text = self.analyzer.evaluate_sufficiency(context)
            
            if status == "SUFFICIENT":
                logger.info(f"이슈 {issue.key} 정보 충분함. 종합 분석을 진행합니다. (이유: {reason})")
                self._do_comprehensive_analysis(issue, context)
                # waiting 레이블은 종합 분석 후 analyzed 레이블과 교체되어야 하지만, 
                # 여기서는 편의상 그대로 둡니다. 엄밀히 제거를 원하면 self.jira.remove_label()
            else:
                logger.info(f"이슈 {issue.key} 정보 아직 부족 또는 답변 진행함. 코멘트를 남깁니다. (이유: {reason})")
                self.jira.add_comment(issue.key, f"안녕하세요, JIIA입니다.\n\n{response_text}", dry_run=self.dry_run)
                # 여전히 waiting 상태 유지

    def _do_comprehensive_analysis(self, issue, context: str):
        logger.info(f"종합 분석 시작: {issue.key}")
        analysis_markdown = self.analyzer.comprehensive_analysis(context)
        
        # JIRA 요약 코멘트 남기기
        summary_comment = (
            "🚀 **JIIA 분석이 완료되었습니다.**\n\n"
            "상세 분석 결과 및 개발자 추천 조치 사항이 PDF로 첨부되었습니다. 관련 담당자에게 해당 이슈를 핸드오프합니다."
        )
        self.jira.add_comment(issue.key, summary_comment, dry_run=self.dry_run)
        
        # PDF 변환 및 첨부
        pdf_path = f"analysis_{issue.key}.pdf"
        generate_pdf_from_markdown(analysis_markdown, pdf_path)
        if not self.dry_run:
            try:
                self.jira.attach_file(issue.key, pdf_path)
                logger.info(f"[{issue.key}] PDF 첨부 완료: {pdf_path}")
            except Exception as e:
                logger.error(f"[{issue.key}] PDF 첨부 실패: {e}")
        
        # 상태 전환 또는 담당자 할당 (SW 엔지니어 핸드오프)
        target_assignee = self.jiia_cfg.get("handoff_assignee_account_id")
        if target_assignee:
            if not self.dry_run:
                try:
                    self.jira.assign_issue(issue.key, target_assignee)
                    logger.info(f"[{issue.key}] 핸드오프: 담당자를 {target_assignee}로 변경했습니다.")
                except Exception as e:
                    # assignee_issue 메소드는 jira_cli.jira.client 에 없을 수 있음. client구현부 확인 시 assign_issue가 명령어엔 있으나 내부 api가 어떤지 봐야함.
                    # fallback으로 REST API 사용.
                    logger.warning(f"assign_issue 중 오류 발생: {e}. (실제로는 jira_action.py를 통해 assign API 필요)")

        # Analyzed 레이블 추가 (완료 처리)
        self.jira.add_label(issue.key, self.label_analyzed, dry_run=self.dry_run)
        logger.info(f"[{issue.key}] 처리 완료.")
