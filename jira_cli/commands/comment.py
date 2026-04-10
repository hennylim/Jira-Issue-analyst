"""
commands/comment.py
-------------------
댓글 관련 CLI 명령어 구현.
"""

import json
from typing import Any

from jira.client import JiraClient, JiraApiError
from utils.logger import get_logger

logger = get_logger("jira_cli.cmd.comment")


def cmd_add_comment(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈에 댓글을 추가합니다."""
    key  = args.key
    text = args.text
    try:
        comment = client.add_comment(key, text)
        print(f"✅ 댓글 추가 완료  [ID: {comment.id}]")
        print(f"   {comment.author}  ({comment.created})")
        print(f"   {comment.body[:200]}")
        return 0
    except JiraApiError as e:
        logger.error("댓글 추가 실패: %s", e)
        return 1


def cmd_list_comments(client: JiraClient, args: Any, cfg: Any) -> int:
    """이슈의 댓글 목록을 조회합니다."""
    key = args.key
    try:
        comments = client.get_comments(key)
        if not comments:
            print("💬 댓글이 없습니다.")
            return 0

        fmt = getattr(args, "format", None) or cfg.get("output.format", "table")
        if fmt == "json":
            print(json.dumps(
                [{"id": c.id, "author": str(c.author), "body": c.body, "created": c.created}
                 for c in comments],
                ensure_ascii=False, indent=2
            ))
        else:
            print(f"💬 댓글 {len(comments)}건 [{key}]")
            print("─" * 60)
            for c in comments:
                print(f"[{c.id}] {c.author}  ({c.created})")
                print(f"  {c.body[:300]}")
                print()
        return 0
    except JiraApiError as e:
        logger.error("댓글 조회 실패: %s", e)
        return 1


def cmd_update_comment(client: JiraClient, args: Any, cfg: Any) -> int:
    """기존 댓글을 수정합니다."""
    key        = args.key
    comment_id = args.comment_id
    text       = args.text
    try:
        comment = client.update_comment(key, comment_id, text)
        print(f"✅ 댓글 수정 완료  [ID: {comment.id}]")
        return 0
    except JiraApiError as e:
        logger.error("댓글 수정 실패: %s", e)
        return 1


def cmd_delete_comment(client: JiraClient, args: Any, cfg: Any) -> int:
    """댓글을 삭제합니다."""
    key        = args.key
    comment_id = args.comment_id

    if not getattr(args, "yes", False):
        confirm = input(f"댓글 {comment_id}을 삭제하시겠습니까? (y/N): ").strip().lower()
        if confirm != "y":
            print("취소되었습니다.")
            return 0

    try:
        client.delete_comment(key, comment_id)
        print(f"✅ 댓글 삭제 완료  [ID: {comment_id}]")
        return 0
    except JiraApiError as e:
        logger.error("댓글 삭제 실패: %s", e)
        return 1
