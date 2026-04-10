"""
commands/issue.py
-----------------
이슈 관련 CLI 명령어 구현.
"""

import json
import sys
from typing import Any

from jira.client import JiraClient, JiraApiError
from jira.models import JiraIssue
from utils.logger import get_logger

logger = get_logger("jira_cli.cmd.issue")


def _format_issue_table(issue: JiraIssue, date_fmt: str = "%Y-%m-%d %H:%M") -> str:
    """이슈 정보를 보기 좋은 텍스트로 포맷합니다."""
    lines = [
        f"{'─'*60}",
        f"  키      : {issue.key}",
        f"  제목    : {issue.summary}",
        f"  상태    : {issue.status}",
        f"  유형    : {issue.issue_type}",
        f"  우선순위: {issue.priority}",
        f"  담당자  : {issue.assignee}",
        f"  보고자  : {issue.reporter}",
        f"  레이블  : {', '.join(issue.labels) or '(없음)'}",
        f"  생성일  : {issue.created}",
        f"  수정일  : {issue.updated}",
        f"{'─'*60}",
    ]
    if issue.description:
        lines.insert(-1, f"  설명:\n  {issue.description[:300]}")
    return "\n".join(lines)


def cmd_get_issue(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈 상세 조회."""
    key = args.key
    fmt = getattr(args, "format", None) or cfg.get("output.format", "table")
    try:
        issue = client.get_issue(key)
        if fmt == "json":
            print(json.dumps(issue.raw, ensure_ascii=False, indent=2))
        else:
            print(_format_issue_table(issue))
        return 0
    except JiraApiError as e:
        logger.error("이슈 조회 실패: %s", e)
        return 1


def cmd_search_issues(client: JiraClient, args: Any, cfg: Any) -> int:
    """JQL 또는 프로젝트로 이슈 검색."""
    jql = args.jql if hasattr(args, "jql") and args.jql else None
    project = getattr(args, "project", None) or cfg.get("defaults.project_key", "")
    status  = getattr(args, "status", None)
    assignee = getattr(args, "assignee", None)
    max_results = getattr(args, "max", None) or cfg.get("defaults.max_results", 50)

    if not jql:
        parts = []
        if project:
            parts.append(f"project = {project}")
        if status:
            parts.append(f'status = "{status}"')
        if assignee:
            parts.append(f"assignee = {assignee}")
        jql = " AND ".join(parts) if parts else "order by updated DESC"

    try:
        issues = client.search_issues(jql, max_results=int(max_results))
        if not issues:
            print("⚠️  검색 결과가 없습니다.")
            return 0

        fmt = getattr(args, "format", None) or cfg.get("output.format", "table")
        if fmt == "json":
            print(json.dumps([i.raw for i in issues], ensure_ascii=False, indent=2))
        else:
            header = f"{'KEY':<14} {'STATUS':<18} {'PRIORITY':<10} {'ASSIGNEE':<20} SUMMARY"
            print(header)
            print("─" * 90)
            for i in issues:
                assignee_str = str(i.assignee)[:18]
                summary_str  = i.summary[:40]
                print(
                    f"{i.key:<14} {str(i.status):<18} {i.priority:<10} "
                    f"{assignee_str:<20} {summary_str}"
                )
            print(f"\n총 {len(issues)}건")
        return 0
    except JiraApiError as e:
        logger.error("이슈 검색 실패: %s", e)
        return 1


def cmd_create_issue(client: JiraClient, args: Any, cfg: Any) -> int:
    """새 이슈 생성."""
    project   = getattr(args, "project", None) or cfg.get("defaults.project_key", "")
    summary   = args.summary
    itype     = getattr(args, "type", None) or cfg.get("defaults.issue_type", "Task")
    desc      = getattr(args, "description", None) or ""
    priority  = getattr(args, "priority", None) or cfg.get("defaults.priority", "")
    labels    = getattr(args, "labels", None) or []
    due_date  = getattr(args, "due_date", None) or ""

    if not project:
        print("❌ 프로젝트 키가 필요합니다 (-p 또는 config defaults.project_key)")
        return 1

    # due_date 형식 검증 (YYYY-MM-DD)
    if due_date:
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
            print(f"❌ 날짜 형식 오류: '{due_date}' → YYYY-MM-DD 형식으로 입력하세요. (예: 2026-04-30)")
            return 1

    try:
        issue = client.create_issue(
            project_key=project,
            summary=summary,
            issue_type=itype,
            description=desc,
            priority=priority,
            labels=labels.split(",") if isinstance(labels, str) else labels,
            due_date=due_date,
        )
        print(f"✅ 이슈 생성 완료: {issue.key}  '{issue.summary}'")
        if due_date:
            print(f"   📅 기한: {due_date}")
        return 0
    except JiraApiError as e:
        logger.error("이슈 생성 실패: %s", e)
        return 1


def cmd_update_issue(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈 필드 업데이트."""
    key         = args.key
    summary     = getattr(args, "summary", None)
    description = getattr(args, "description", None)
    priority    = getattr(args, "priority", None)
    labels      = getattr(args, "labels", None)
    due_date    = getattr(args, "due_date", None)
    if isinstance(labels, str):
        labels = labels.split(",")

    # due_date 형식 검증
    if due_date:
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
            print(f"❌ 날짜 형식 오류: '{due_date}' → YYYY-MM-DD 형식으로 입력하세요. (예: 2026-04-30)")
            return 1

    try:
        success = client.update_issue(
            key,
            summary=summary,
            description=description,
            priority=priority,
            labels=labels,
            due_date=due_date,
        )
        if success:
            print(f"✅ 이슈 업데이트 완료: {key}")
        return 0 if success else 1
    except JiraApiError as e:
        logger.error("이슈 업데이트 실패: %s", e)
        return 1


def cmd_copy_issue(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈를 다른 프로젝트로 복사합니다."""
    import re

    source_key     = args.key
    target_project = args.target_project
    fmt            = getattr(args, "format", None) or cfg.get("output.format", "table")

    # 옵션 수집
    summary_prefix   = getattr(args, "summary_prefix",   "") or ""
    summary_suffix   = getattr(args, "summary_suffix",   "") or ""
    override_summary = getattr(args, "summary",          "") or ""
    override_type    = getattr(args, "type",             "") or ""
    override_priority= getattr(args, "priority",         "") or ""
    override_assignee= getattr(args, "assignee",         "") or ""
    override_due_date= getattr(args, "due_date",         "") or ""
    copy_comments    = getattr(args, "copy_comments",    False)
    copy_subtasks    = getattr(args, "copy_subtasks",    False)
    no_labels        = getattr(args, "no_labels",        False)
    no_description   = getattr(args, "no_description",  False)
    no_link          = getattr(args, "no_link",          False)

    # 날짜 형식 검증
    if override_due_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", override_due_date):
        print(f"❌ 날짜 형식 오류: '{override_due_date}' → YYYY-MM-DD 형식으로 입력하세요.")
        return 1

    # 복사 전 미리보기
    print(f"📋 이슈 복사 시작")
    print(f"   원본  : {source_key}")
    print(f"   대상  : {target_project}")
    if copy_comments:   print("   댓글  : 복사함")
    if copy_subtasks:   print("   서브태스크: 재귀 복사")
    if no_link:         print("   링크  : 생성 안 함")
    print()

    try:
        result = client.copy_issue(
            source_key        = source_key,
            target_project    = target_project,
            summary_prefix    = summary_prefix,
            summary_suffix    = summary_suffix,
            override_summary  = override_summary,
            override_type     = override_type,
            override_priority = override_priority,
            override_assignee = override_assignee,
            override_due_date = override_due_date,
            copy_labels       = not no_labels,
            copy_description  = not no_description,
            copy_comments     = copy_comments,
            copy_subtasks     = copy_subtasks,
            link_to_source    = not no_link,
        )

        if fmt == "json":
            import json
            print(json.dumps({
                "source":           result.source.key,
                "new_issue":        result.new_issue.key,
                "summary":          result.new_issue.summary,
                "copied_comments":  result.copied_comments,
                "copied_subtasks":  result.copied_subtasks,
            }, ensure_ascii=False, indent=2))
        else:
            print(f"✅ 복사 완료!")
            print(f"   원본  : {result.source.key}  '{result.source.summary}'")
            print(f"   신규  : {result.new_issue.key}  '{result.new_issue.summary}'")
            if result.copied_comments:
                print(f"   댓글  : {result.copied_comments}개 복사")
            if result.copied_subtasks:
                print(f"   서브태스크: {', '.join(result.copied_subtasks)}")
            if not no_link:
                print(f"   링크  : {result.new_issue.key} → (Clones) → {result.source.key}")

        return 0

    except JiraApiError as e:
        logger.error("이슈 복사 실패: %s", e)
        print(f"❌ 이슈 복사 실패: {e}")
        return 1
