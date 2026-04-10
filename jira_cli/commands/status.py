"""
commands/status.py
------------------
이슈 상태 전환 CLI 명령어 구현.
"""

import json
from typing import Any

from jira.client import JiraClient, JiraApiError
from utils.logger import get_logger

logger = get_logger("jira_cli.cmd.status")


def cmd_change_status(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈 상태를 변경합니다."""
    key     = args.key
    status  = args.status
    comment = getattr(args, "comment", "") or ""

    # config 에 정의된 상태 별칭 맵 전달
    transition_map = cfg.get_section("transitions") if hasattr(cfg, "get_section") else {}

    try:
        client.transition_issue(key, status, comment=comment, transition_map=transition_map)
        issue = client.get_issue(key, fields=["status", "summary"])
        print(f"✅ 상태 변경 완료: {key}  → [{issue.status}]  '{issue.summary}'")
        if comment:
            print(f"   💬 댓글 추가됨: {comment[:80]}")
        return 0
    except JiraApiError as e:
        logger.error("상태 변경 실패: %s", e)
        return 1


def cmd_list_transitions(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈에서 가능한 상태 전환 목록을 조회합니다."""
    key = args.key
    try:
        transitions = client.get_transitions(key)
        if not transitions:
            print("⚠️  가능한 상태 전환이 없습니다.")
            return 0

        fmt = getattr(args, "format", None) or cfg.get("output.format", "table")
        if fmt == "json":
            print(json.dumps(
                [{"id": t.id, "name": t.name, "to": t.to_status} for t in transitions],
                ensure_ascii=False, indent=2
            ))
        else:
            print(f"🔄 가능한 전환 [{key}]")
            print(f"  {'ID':<6} {'전환 이름':<25} 목표 상태")
            print("  " + "─" * 50)
            for t in transitions:
                print(f"  {t.id:<6} {t.name:<25} {t.to_status}")
        return 0
    except JiraApiError as e:
        logger.error("전환 조회 실패: %s", e)
        return 1


def cmd_assign_issue(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈 담당자를 변경합니다."""
    key        = args.key
    account_id = getattr(args, "account_id", "") or ""
    try:
        client.assign_issue(key, account_id)
        if account_id:
            print(f"✅ 담당자 변경 완료: {key}  → {account_id}")
        else:
            print(f"✅ 담당자 해제 완료: {key}")
        return 0
    except JiraApiError as e:
        logger.error("담당자 변경 실패: %s", e)
        return 1


def cmd_add_label(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈에 레이블을 추가합니다."""
    key   = args.key
    label = args.label
    try:
        client.add_label(key, label)
        print(f"✅ 레이블 추가 완료: {key}  + '{label}'")
        return 0
    except JiraApiError as e:
        logger.error("레이블 추가 실패: %s", e)
        return 1


def cmd_remove_label(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈에서 레이블을 제거합니다."""
    key   = args.key
    label = args.label
    try:
        client.remove_label(key, label)
        print(f"✅ 레이블 제거 완료: {key}  - '{label}'")
        return 0
    except JiraApiError as e:
        logger.error("레이블 제거 실패: %s", e)
        return 1
