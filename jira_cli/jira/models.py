"""
jira/models.py
--------------
JIRA API 응답을 감싸는 경량 데이터 모델.
dict 직접 접근 없이 .속성 으로 사용 가능.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class JiraUser:
    account_id: str = ""
    display_name: str = ""
    email: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> "JiraUser":
        if not d:
            return cls()
        return cls(
            account_id=d.get("accountId", d.get("name", "")),
            display_name=d.get("displayName", ""),
            email=d.get("emailAddress", ""),
        )

    def __str__(self) -> str:
        return self.display_name or self.account_id or "Unknown"


@dataclass
class JiraStatus:
    id: str = ""
    name: str = ""
    category: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> "JiraStatus":
        if not d:
            return cls()
        cat = d.get("statusCategory", {})
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            category=cat.get("name", ""),
        )

    def __str__(self) -> str:
        return self.name


@dataclass
class JiraTransition:
    id: str = ""
    name: str = ""
    to_status: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "JiraTransition":
        to = d.get("to", {})
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            to_status=to.get("name", ""),
        )

    def __str__(self) -> str:
        return f"{self.name} → {self.to_status}"


@dataclass
class JiraComment:
    id: str = ""
    author: JiraUser = field(default_factory=JiraUser)
    body: str = ""
    created: str = ""
    updated: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "JiraComment":
        # API v3 body 는 ADF(Atlassian Document Format) 객체
        body = d.get("body", "")
        if isinstance(body, dict):
            # ADF → plain text 단순 추출
            body = _extract_adf_text(body)
        return cls(
            id=d.get("id", ""),
            author=JiraUser.from_dict(d.get("author")),
            body=body,
            created=d.get("created", "")[:16],
            updated=d.get("updated", "")[:16],
        )

    def __str__(self) -> str:
        return f"[{self.created}] {self.author}: {self.body[:80]}"


@dataclass
class JiraIssue:
    key: str = ""
    id: str = ""
    summary: str = ""
    status: JiraStatus = field(default_factory=JiraStatus)
    assignee: JiraUser = field(default_factory=JiraUser)
    reporter: JiraUser = field(default_factory=JiraUser)
    priority: str = ""
    issue_type: str = ""
    labels: list[str] = field(default_factory=list)
    created: str = ""
    updated: str = ""
    due_date: str = ""
    description: str = ""
    comments: list[JiraComment] = field(default_factory=list)
    subtasks: list[str] = field(default_factory=list)   # 서브태스크 키 목록
    parent_key: str = ""                                  # 부모 이슈 키 (에픽/서브태스크)
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "JiraIssue":
        f = d.get("fields", {})
        # description: v3=ADF, v2=string
        desc = f.get("description", "") or ""
        if isinstance(desc, dict):
            desc = _extract_adf_text(desc)

        comments_raw = (f.get("comment") or {}).get("comments", [])
        subtasks     = [s.get("key", "") for s in (f.get("subtasks") or [])]
        parent_key   = (f.get("parent") or {}).get("key", "")

        return cls(
            key=d.get("key", ""),
            id=d.get("id", ""),
            summary=f.get("summary", ""),
            status=JiraStatus.from_dict(f.get("status")),
            assignee=JiraUser.from_dict(f.get("assignee")),
            reporter=JiraUser.from_dict(f.get("reporter")),
            priority=(f.get("priority") or {}).get("name", ""),
            issue_type=(f.get("issuetype") or {}).get("name", ""),
            labels=f.get("labels", []),
            created=(f.get("created") or "")[:16],
            updated=(f.get("updated") or "")[:16],
            due_date=(f.get("duedate") or ""),
            description=desc,
            comments=[JiraComment.from_dict(c) for c in comments_raw],
            subtasks=subtasks,
            parent_key=parent_key,
            raw=d,
        )

    def __str__(self) -> str:
        return f"{self.key}: {self.summary} [{self.status}]"


@dataclass
class CopyResult:
    """이슈 복사 작업 결과."""
    source: "JiraIssue" = field(default_factory=lambda: JiraIssue())
    new_issue: "JiraIssue" = field(default_factory=lambda: JiraIssue())
    copied_comments: int = 0
    copied_subtasks: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"복사 완료: {self.source.key} → {self.new_issue.key}",
            f"  제목    : {self.new_issue.summary}",
        ]
        if self.copied_comments:
            lines.append(f"  댓글    : {self.copied_comments}개 복사")
        if self.copied_subtasks:
            lines.append(f"  서브태스크: {', '.join(self.copied_subtasks)}")
        return "\n".join(lines)



# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _extract_adf_text(node: Any, depth: int = 0) -> str:
    """Atlassian Document Format(ADF) 객체에서 텍스트를 재귀적으로 추출합니다."""
    if depth > 20:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type", "")
    parts: list[str] = []

    if node_type == "text":
        parts.append(node.get("text", ""))
    elif node_type in ("hardBreak", "rule"):
        parts.append("\n")

    for child in node.get("content", []):
        parts.append(_extract_adf_text(child, depth + 1))

    return "".join(parts)
