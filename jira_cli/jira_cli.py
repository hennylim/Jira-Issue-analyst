#!/usr/bin/env python3
"""
jira_cli.py
-----------
JIRA 관리 CLI 툴 메인 진입점.

사용법:
  python jira_cli.py <명령어> [옵션]

예시:
  python jira_cli.py ping
  python jira_cli.py issue get PROJ-123
  python jira_cli.py issue search -p PROJ --status "In Progress"
  python jira_cli.py issue create -p PROJ -s "새 작업" -t Task
  python jira_cli.py comment add PROJ-123 "작업 시작했습니다."
  python jira_cli.py comment list PROJ-123
  python jira_cli.py status change PROJ-123 "In Progress"
  python jira_cli.py status transitions PROJ-123
  python jira_cli.py status assign PROJ-123 --account-id user123
  python jira_cli.py label add PROJ-123 bug
  python jira_cli.py label remove PROJ-123 bug
"""

import argparse
import sys
import os

# ── 경로 설정 (패키지 구조 없이 단독 실행 지원) ─────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from utils.config_loader import ConfigLoader
from utils.logger import setup_logger, get_logger
from jira.client import JiraClient, JiraApiError


# ── 명령어 임포트 ─────────────────────────────────────────────────────────────
from commands.issue   import (cmd_get_issue, cmd_search_issues,
                               cmd_create_issue, cmd_update_issue,
                               cmd_copy_issue)
from commands.comment import (cmd_add_comment, cmd_list_comments,
                               cmd_update_comment, cmd_delete_comment)
from commands.status  import (cmd_change_status, cmd_list_transitions,
                               cmd_assign_issue, cmd_add_label, cmd_remove_label)


# ─────────────────────────────────────────────────────────────────────────────
#  파서 구성
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jira_cli",
        description="🔧 JIRA 관리 CLI 툴",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── 공통 옵션 ──────────────────────────────────────────────────────────
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="설정 파일 경로 (기본: config.yaml)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="DEBUG 레벨 로그 출력",
    )

    # ── 공유 부모 파서: 출력 형식 옵션 (모든 서브커맨드에 상속) ──────────────
    fmt_parent = argparse.ArgumentParser(add_help=False)
    fmt_parent.add_argument(
        "-f", "--format",
        choices=["table", "json"],
        default=None,
        help="출력 형식 (기본: table)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ── ping ──────────────────────────────────────────────────────────────
    subparsers.add_parser("ping", help="JIRA 서버 연결 확인")

    # ── issue ─────────────────────────────────────────────────────────────
    issue_p = subparsers.add_parser("issue", help="이슈 관리")
    issue_sub = issue_p.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    issue_sub.required = True

    # issue get
    p = issue_sub.add_parser("get", help="이슈 상세 조회", parents=[fmt_parent])
    p.add_argument("key", help="이슈 키 (예: PROJ-123)")

    # issue search
    p = issue_sub.add_parser("search", help="JQL / 조건으로 이슈 검색", parents=[fmt_parent])
    p.add_argument("jql", nargs="?", default=None, help="JQL 쿼리 (선택)")
    p.add_argument("-p", "--project", default=None, help="프로젝트 키")
    p.add_argument("-s", "--status",  default=None, help="상태 필터")
    p.add_argument("-a", "--assignee",default=None, help="담당자 필터")
    p.add_argument("-m", "--max",     default=None, type=int, help="최대 결과 수")

    # issue create
    p = issue_sub.add_parser("create", help="이슈 생성")
    p.add_argument("-p", "--project",     required=False, default=None, help="프로젝트 키")
    p.add_argument("-s", "--summary",     required=True,               help="이슈 제목")
    p.add_argument("-t", "--type",        default=None,                help="이슈 유형")
    p.add_argument("-d", "--description", default=None,                help="설명")
    p.add_argument("--priority",          default=None,                help="우선순위")
    p.add_argument("--labels",            default=None,                help="레이블 (쉼표 구분)")
    p.add_argument("--due-date",          default=None, dest="due_date",
                   metavar="YYYY-MM-DD",  help="기한 (예: 2026-04-30)")

    # issue update
    p = issue_sub.add_parser("update", help="이슈 필드 수정")
    p.add_argument("key",                                    help="이슈 키")
    p.add_argument("-s", "--summary",     default=None,     help="새 제목")
    p.add_argument("-d", "--description", default=None,     help="새 설명")
    p.add_argument("--priority",          default=None,     help="우선순위")
    p.add_argument("--labels",            default=None,     help="레이블 (쉼표 구분)")
    p.add_argument("--due-date",          default=None, dest="due_date",
                   metavar="YYYY-MM-DD",  help="기한 (예: 2026-04-30)")

    # issue copy
    p = issue_sub.add_parser("copy", help="이슈를 다른 프로젝트로 복사", parents=[fmt_parent])
    p.add_argument("key",            help="복사할 원본 이슈 키 (예: SI-100)")
    p.add_argument("target_project", help="대상 프로젝트 키 (예: OPS)")
    p.add_argument("--summary",          default=None, help="새 제목 (미지정 시 원본 제목 사용)")
    p.add_argument("--summary-prefix",   default="",   dest="summary_prefix",
                   help="제목 앞에 추가할 텍스트 (예: '[복사] ')")
    p.add_argument("--summary-suffix",   default="",   dest="summary_suffix",
                   help="제목 뒤에 추가할 텍스트 (예: ' (복사본)')")
    p.add_argument("-t", "--type",       default=None, help="이슈 유형 변경")
    p.add_argument("--priority",         default=None, help="우선순위 변경")
    p.add_argument("--assignee",         default=None, help="담당자 account_id 변경")
    p.add_argument("--due-date",         default=None, dest="due_date",
                   metavar="YYYY-MM-DD", help="기한 변경")
    p.add_argument("--copy-comments",    action="store_true", dest="copy_comments",
                   help="댓글도 함께 복사")
    p.add_argument("--copy-subtasks",    action="store_true", dest="copy_subtasks",
                   help="서브태스크도 재귀 복사")
    p.add_argument("--no-labels",        action="store_true", dest="no_labels",
                   help="레이블 복사 안 함")
    p.add_argument("--no-description",   action="store_true", dest="no_description",
                   help="설명 복사 안 함")
    p.add_argument("--no-link",          action="store_true", dest="no_link",
                   help="원본 이슈에 링크 생성 안 함")

    # ── comment ───────────────────────────────────────────────────────────
    comment_p = subparsers.add_parser("comment", help="댓글 관리")
    comment_sub = comment_p.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    comment_sub.required = True

    p = comment_sub.add_parser("add",    help="댓글 추가")
    p.add_argument("key",  help="이슈 키")
    p.add_argument("text", help="댓글 내용")

    p = comment_sub.add_parser("list",   help="댓글 목록 조회", parents=[fmt_parent])
    p.add_argument("key", help="이슈 키")

    p = comment_sub.add_parser("update", help="댓글 수정")
    p.add_argument("key",        help="이슈 키")
    p.add_argument("comment_id", help="댓글 ID")
    p.add_argument("text",       help="수정할 댓글 내용")

    p = comment_sub.add_parser("delete", help="댓글 삭제")
    p.add_argument("key",        help="이슈 키")
    p.add_argument("comment_id", help="댓글 ID")
    p.add_argument("-y", "--yes", action="store_true", help="확인 없이 삭제")

    # ── status ────────────────────────────────────────────────────────────
    status_p = subparsers.add_parser("status", help="이슈 상태 관리")
    status_sub = status_p.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    status_sub.required = True

    p = status_sub.add_parser("change", help="상태 변경")
    p.add_argument("key",    help="이슈 키")
    p.add_argument("status", help="목표 상태 (예: 'In Progress', 'done')")
    p.add_argument("-c", "--comment", default=None, help="상태 변경 댓글")

    p = status_sub.add_parser("transitions", help="가능한 상태 전환 목록", parents=[fmt_parent])
    p.add_argument("key", help="이슈 키")

    p = status_sub.add_parser("assign", help="담당자 변경")
    p.add_argument("key", help="이슈 키")
    p.add_argument("--account-id", dest="account_id", default="",
                   help="담당자 Account ID (비워두면 담당자 해제)")

    # ── label ─────────────────────────────────────────────────────────────
    label_p = subparsers.add_parser("label", help="레이블 관리")
    label_sub = label_p.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    label_sub.required = True

    p = label_sub.add_parser("add",    help="레이블 추가")
    p.add_argument("key",   help="이슈 키")
    p.add_argument("label", help="추가할 레이블")

    p = label_sub.add_parser("remove", help="레이블 제거")
    p.add_argument("key",   help="이슈 키")
    p.add_argument("label", help="제거할 레이블")

    return parser


# ─────────────────────────────────────────────────────────────────────────────
#  명령어 디스패처
# ─────────────────────────────────────────────────────────────────────────────

DISPATCH = {
    ("ping",    None):           lambda c, a, g: (_ping(c), 0)[1],
    # issue
    ("issue",   "get"):          cmd_get_issue,
    ("issue",   "search"):       cmd_search_issues,
    ("issue",   "create"):       cmd_create_issue,
    ("issue",   "update"):       cmd_update_issue,
    ("issue",   "copy"):         cmd_copy_issue,
    # comment
    ("comment", "add"):          cmd_add_comment,
    ("comment", "list"):         cmd_list_comments,
    ("comment", "update"):       cmd_update_comment,
    ("comment", "delete"):       cmd_delete_comment,
    # status
    ("status",  "change"):       cmd_change_status,
    ("status",  "transitions"):  cmd_list_transitions,
    ("status",  "assign"):       cmd_assign_issue,
    # label
    ("label",   "add"):          cmd_add_label,
    ("label",   "remove"):       cmd_remove_label,
}


def _ping(client: JiraClient) -> None:
    info = client.ping()
    print(f"✅ 연결 성공!")
    print(f"   서버  : {info.get('serverTitle', 'JIRA')}")
    print(f"   버전  : {info.get('version', 'unknown')}")
    print(f"   배포  : {info.get('deploymentType', 'unknown')}")
    print(f"   URL   : {info.get('baseUrl', '')}")


# ─────────────────────────────────────────────────────────────────────────────
#  메인
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    # ── 설정 로드 ──────────────────────────────────────────────────────────
    cfg = ConfigLoader(args.config)

    # ── 로거 초기화 ────────────────────────────────────────────────────────
    log_cfg = cfg.get_section("logging")
    if args.debug:
        log_cfg["level"] = "DEBUG"
    logger = setup_logger("jira_cli", log_cfg)
    logger.debug("Config loaded from: %s", cfg.config_path)

    # ── JIRA 클라이언트 초기화 ─────────────────────────────────────────────
    try:
        client = JiraClient.from_config(cfg)
    except Exception as e:
        logger.error("JiraClient 초기화 실패: %s", e)
        print(f"❌ 클라이언트 초기화 실패: {e}")
        print("   config.yaml 의 jira 설정을 확인하세요.")
        return 1

    # ── 명령어 디스패치 ────────────────────────────────────────────────────
    sub = getattr(args, "subcommand", None)
    handler = DISPATCH.get((args.command, sub))

    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(client, args, cfg) or 0
    except JiraApiError as e:
        logger.error("API 오류: %s", e)
        print(f"❌ API 오류: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n중단되었습니다.")
        return 130
    except Exception as e:
        logger.exception("예기치 않은 오류: %s", e)
        print(f"❌ 오류: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
