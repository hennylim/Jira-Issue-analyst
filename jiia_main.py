import argparse
import logging
import sys
import os

# sys.path 설정: 현재 폴더를 패스에 추가하여 ai_chat과 jira_cli 모듈 직접 임포트 지원
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jira_cli.utils.config_loader import ConfigLoader
from core.workflow import JIIAWorkflow

def setup_logging(config):
    log_cfg = config.get("logging", {})
    level_str = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    
    log_dir = log_cfg.get("dir", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 루트 로거 설정
    logger = logging.getLogger()
    logger.setLevel(level)
    
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s')
    
    # 콘솔 핸들러
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # 파일 핸들러 (디버깅 지원용 파일 로깅)
    fh = logging.FileHandler(os.path.join(log_dir, 'jiia_agent.log'), encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

def main():
    parser = argparse.ArgumentParser(description="JIIA (Jira Intelligent Issue Analyst) System")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Run without actually commenting or modifying Jira issues")
    parser.add_argument("--run-once", action="store_true", help="Run the workflow once and exit (e.g. for cron)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.config):
        print(f"[Error] Config file not found: {args.config}")
        sys.exit(1)
        
    loader = ConfigLoader(args.config)
    config_dict = loader.config
    
    setup_logging(config_dict)
    logger = logging.getLogger(__name__)
    
    logger.info("="*50)
    logger.info(f"JIIA Agent Starting (Dry-Run: {args.dry_run})")
    logger.info("="*50)
    
    workflow = JIIAWorkflow(config_dict, args.config)
    
    if args.run_once:
        logger.info("Mode: Run-once")
        workflow.dry_run = args.dry_run
        workflow.process_tickets()
        logger.info("Run-once completed.")
    else:
        logger.info("Mode: Polling daemon")
        try:
            workflow.start_polling(dry_run=args.dry_run)
        except KeyboardInterrupt:
            logger.info("JIIA Agent stopped by user.")

if __name__ == "__main__":
    main()
