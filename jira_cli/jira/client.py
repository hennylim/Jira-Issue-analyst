"""
jira/client.py
--------------
재사용 가능한 JiraClient 클래스.
다른 파이썬 프로그램에서 쉽게 import 하여 사용 가능.

Example
-------
from jira.client import JiraClient
from utils.config_loader import ConfigLoader

cfg    = ConfigLoader("config.yaml")
client = JiraClient.from_config(cfg)

issue    = client.get_issue("PROJ-123")
comments = client.get_comments("PROJ-123")
client.add_comment("PROJ-123", "작업 완료했습니다.")
client.transition_issue("PROJ-123", "In Progress")
"""

from __future__ import annotations

from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth

from jira.api_handler import ApiHandler, JiraApiError
from jira.models import JiraComment, JiraIssue, JiraTransition, CopyResult
from utils.logger import get_logger


class TokenAuth(requests.auth.AuthBase):
    """Bearer / PAT 토큰 인증."""
    def __init__(self, token: str):
        self._token = token

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self._token}"
        return r


class JiraClient:
    """
    JIRA REST API 클라이언트.

    Parameters
    ----------
    base_url    : JIRA URL (예: https://your-domain.atlassian.net)
    auth_type   : "token" | "pat" | "basic"
    email       : Cloud 계정 이메일 (token 방식)
    api_token   : API Token (token 방식) 또는 PAT (pat 방식)
    username    : 사용자명 (basic 방식)
    password    : 비밀번호 (basic 방식)
    api_version : "auto" | "2" | "3"
    timeout     : 요청 타임아웃 (초)
    verify_ssl  : SSL 검증 여부
    max_retries : 재시도 횟수
    """

    def __init__(
        self,
        base_url: str,
        auth_type: str = "token",
        email: str = "",
        api_token: str = "",
        username: str = "",
        password: str = "",
        pat: str = "",
        api_version: str = "auto",
        timeout: int = 30,
        verify_ssl: bool = True,
        max_retries: int = 3,
    ):
        self._logger = get_logger("jira_cli.client")
        auth = self._build_auth(auth_type, email, api_token, username, password, pat)

        self._api = ApiHandler(
            base_url=base_url,
            auth=auth,
            api_version=api_version,
            timeout=timeout,
            verify_ssl=verify_ssl,
            max_retries=max_retries,
        )
        self._logger.info("JiraClient ready  [%s]  API v%s", base_url, self._api.api_version)

    # ── 팩토리 메서드 ────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, cfg: Any) -> "JiraClient":
        """
        ConfigLoader 객체로 JiraClient 를 생성합니다.

        Parameters
        ----------
        cfg : ConfigLoader 인스턴스 (utils.config_loader.ConfigLoader)
        """
        return cls(
            base_url    = cfg.get("jira.base_url", ""),
            auth_type   = cfg.get("jira.auth_type", "token"),
            email       = cfg.get("jira.email", ""),
            api_token   = cfg.get("jira.api_token", ""),
            pat         = cfg.get("jira.pat", ""),
            api_version = cfg.get("jira.api_version", "auto"),
            timeout     = cfg.get("jira.timeout", 30),
            verify_ssl  = cfg.get("jira.verify_ssl", True),
            max_retries = cfg.get("jira.max_retries", 3),
        )

    # ── 이슈 ────────────────────────────────────────────────────────────────

    def get_issue(self, issue_key: str, fields: list[str] | None = None) -> JiraIssue:
        """이슈 정보를 조회합니다."""
        params: dict = {}
        if fields:
            params["fields"] = ",".join(fields)
        self._logger.info("GET issue: %s", issue_key)
        data = self._api.get(f"issue/{issue_key}", params=params)
        return JiraIssue.from_dict(data)

    def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        fields: list[str] | None = None,
        start_at: int = 0,
    ) -> list[JiraIssue]:
        """JQL 쿼리로 이슈 목록을 검색합니다.

        API v3: POST /rest/api/3/search/jql
                - startAt 미지원 → nextPageToken 페이지네이션 (CHANGE-2046)
        API v2: POST /rest/api/2/search
                - startAt / maxResults 기존 방식 유지
        """
        _fields = fields or ["summary", "status", "assignee", "priority", "updated"]

        if self._api.is_v3:
            return self._search_v3(jql, max_results, _fields)
        else:
            return self._search_v2(jql, max_results, _fields, start_at)

    def _search_v3(
        self,
        jql: str,
        max_results: int,
        fields: list[str],
    ) -> list[JiraIssue]:
        """
        POST /rest/api/3/search/jql
        nextPageToken 기반 페이지네이션.
        startAt 은 이 엔드포인트에서 지원되지 않으므로 포함하지 않음.
        """
        search_path = "search/jql"
        all_issues: list[JiraIssue] = []
        next_page_token: str | None = None
        page_size = min(max_results, 100)  # 1회 최대 100건

        self._logger.info("SEARCH v3 [%s]: %s  (max=%d)", search_path, jql, max_results)

        while len(all_issues) < max_results:
            fetch = min(page_size, max_results - len(all_issues))
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": fetch,
                "fields": fields,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            data = self._api.post(search_path, json=body)
            page = [JiraIssue.from_dict(i) for i in data.get("issues", [])]
            all_issues.extend(page)

            next_page_token = data.get("nextPageToken")
            # 마지막 페이지 판단: 결과가 없거나 토큰이 없으면 종료
            if not page or not next_page_token:
                break

        self._logger.info("Found %d issue(s)", len(all_issues))
        return all_issues

    def _search_v2(
        self,
        jql: str,
        max_results: int,
        fields: list[str],
        start_at: int,
    ) -> list[JiraIssue]:
        """POST /rest/api/2/search — startAt 기반 페이지네이션."""
        search_path = "search"
        self._logger.info("SEARCH v2 [%s]: %s  (max=%d)", search_path, jql, max_results)
        body: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
            "fields": fields,
        }
        data = self._api.post(search_path, json=body)
        issues = [JiraIssue.from_dict(i) for i in data.get("issues", [])]
        self._logger.info("Found %d issue(s)", len(issues))
        return issues

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str = "Task",
        description: str = "",
        assignee_id: str = "",
        priority: str = "",
        labels: list[str] | None = None,
        due_date: str = "",
        extra_fields: dict[str, Any] | None = None,
    ) -> JiraIssue:
        """
        새 이슈를 생성합니다.

        Parameters
        ----------
        due_date     : 기한 (YYYY-MM-DD 형식, 예: 2026-04-30)
        extra_fields : 프로젝트별 커스텀 필드 딕셔너리
                       예) {"customfield_10015": "value"}
        """
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = self._api.make_body(description)
        if assignee_id:
            fields["assignee"] = {"accountId": assignee_id}
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = labels
        if due_date:
            fields["duedate"] = due_date  # YYYY-MM-DD
        if extra_fields:
            fields.update(extra_fields)

        self._logger.info("CREATE issue in %s: %s", project_key, summary)
        data = self._api.post("issue", json={"fields": fields})
        return self.get_issue(data["key"])

    def update_issue(
        self,
        issue_key: str,
        summary: str | None = None,
        description: str | None = None,
        assignee_id: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
        due_date: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> bool:
        """이슈 필드를 업데이트합니다."""
        fields: dict[str, Any] = {}
        if summary is not None:
            fields["summary"] = summary
        if description is not None:
            fields["description"] = self._api.make_body(description)
        if assignee_id is not None:
            fields["assignee"] = {"accountId": assignee_id} if assignee_id else None
        if priority is not None:
            fields["priority"] = {"name": priority}
        if labels is not None:
            fields["labels"] = labels
        if due_date is not None:
            fields["duedate"] = due_date  # YYYY-MM-DD, "" 이면 기한 제거
        if extra_fields:
            fields.update(extra_fields)

        if not fields:
            self._logger.warning("update_issue: no fields to update")
            return False

        self._logger.info("UPDATE issue %s: %s", issue_key, list(fields.keys()))
        self._api.put(f"issue/{issue_key}", json={"fields": fields})
        return True

    def attach_file(self, issue_key: str, file_path: str) -> dict:
        """이슈에 파일을 첨부합니다."""
        import os
        self._logger.info("ATTACH file to %s: %s", issue_key, file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        headers = {"X-Atlassian-Token": "no-check"}
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/octet-stream")}
            data = self._api.upload(f"issue/{issue_key}/attachments", files=files, headers=headers)
        return data

    # ── 댓글 ────────────────────────────────────────────────────────────────

    def get_comments(self, issue_key: str) -> list[JiraComment]:
        """이슈의 댓글 목록을 조회합니다."""
        self._logger.info("GET comments: %s", issue_key)
        data = self._api.get(f"issue/{issue_key}/comment")
        return [JiraComment.from_dict(c) for c in data.get("comments", [])]

    def add_comment(self, issue_key: str, text: str) -> JiraComment:
        """이슈에 댓글을 추가합니다."""
        body = {"body": self._api.make_body(text)}
        self._logger.info("ADD comment to %s", issue_key)
        data = self._api.post(f"issue/{issue_key}/comment", json=body)
        return JiraComment.from_dict(data)

    def update_comment(self, issue_key: str, comment_id: str, text: str) -> JiraComment:
        """기존 댓글을 수정합니다."""
        body = {"body": self._api.make_body(text)}
        self._logger.info("UPDATE comment %s on %s", comment_id, issue_key)
        data = self._api.put(f"issue/{issue_key}/comment/{comment_id}", json=body)
        return JiraComment.from_dict(data)

    def delete_comment(self, issue_key: str, comment_id: str) -> bool:
        """댓글을 삭제합니다."""
        self._logger.info("DELETE comment %s on %s", comment_id, issue_key)
        self._api.delete(f"issue/{issue_key}/comment/{comment_id}")
        return True

    # ── 상태 전환 ────────────────────────────────────────────────────────────

    def get_transitions(self, issue_key: str) -> list[JiraTransition]:
        """이슈에서 가능한 상태 전환 목록을 조회합니다."""
        self._logger.info("GET transitions: %s", issue_key)
        data = self._api.get(f"issue/{issue_key}/transitions")
        return [JiraTransition.from_dict(t) for t in data.get("transitions", [])]

    def transition_issue(
        self,
        issue_key: str,
        target_status: str,
        comment: str = "",
        transition_map: dict[str, list[str]] | None = None,
    ) -> bool:
        """
        이슈 상태를 변경합니다.

        Parameters
        ----------
        issue_key     : 이슈 키
        target_status : 원하는 상태명 (예: "In Progress", "done")
        comment       : 상태 변경 시 추가할 댓글
        transition_map: config 의 transitions 섹션 (별칭 지원)
        """
        transitions = self.get_transitions(issue_key)
        transition_id = self._find_transition_id(
            transitions, target_status, transition_map or {}
        )

        if not transition_id:
            available = [str(t) for t in transitions]
            raise JiraApiError(
                f"Transition '{target_status}' not found. "
                f"Available: {available}"
            )

        body: dict[str, Any] = {"transition": {"id": transition_id}}
        if comment:
            body["update"] = {
                "comment": [{"add": {"body": self._api.make_body(comment)}}]
            }

        self._logger.info(
            "TRANSITION %s → '%s' (id=%s)", issue_key, target_status, transition_id
        )
        self._api.post(f"issue/{issue_key}/transitions", json=body)
        return True

    # ── 스프린트 / 프로젝트 ──────────────────────────────────────────────────

    def get_projects(self, max_results: int = 50) -> list[dict]:
        """접근 가능한 프로젝트 목록을 반환합니다."""
        self._logger.info("GET projects")
        data = self._api.get("project", params={"maxResults": max_results})
        if isinstance(data, list):
            return data
        return data.get("values", [])

    def assign_issue(self, issue_key: str, account_id: str) -> bool:
        """이슈 담당자를 변경합니다. account_id='' 이면 담당자 해제."""
        body = {"accountId": account_id} if account_id else {"accountId": None}
        self._logger.info("ASSIGN %s → %s", issue_key, account_id or "(unassigned)")
        self._api.put(f"issue/{issue_key}/assignee", json=body)
        return True

    def add_label(self, issue_key: str, label: str) -> bool:
        """이슈에 레이블을 추가합니다."""
        issue = self.get_issue(issue_key, fields=["labels"])
        existing = issue.labels
        if label not in existing:
            self.update_issue(issue_key, labels=existing + [label])
        return True

    def remove_label(self, issue_key: str, label: str) -> bool:
        """이슈에서 레이블을 제거합니다."""
        issue = self.get_issue(issue_key, fields=["labels"])
        new_labels = [l for l in issue.labels if l != label]
        self.update_issue(issue_key, labels=new_labels)
        return True

    # ── 이슈 복사 ────────────────────────────────────────────────────────────

    def copy_issue(
        self,
        source_key: str,
        target_project: str,
        summary_prefix: str = "",
        summary_suffix: str = "",
        override_summary: str = "",
        override_type: str = "",
        override_priority: str = "",
        override_assignee: str = "",
        override_due_date: str = "",
        copy_labels: bool = True,
        copy_description: bool = True,
        copy_comments: bool = False,
        copy_subtasks: bool = False,
        link_to_source: bool = True,
        extra_fields: dict[str, Any] | None = None,
    ) -> "CopyResult":
        """
        이슈를 다른 프로젝트로 복사합니다.

        Parameters
        ----------
        source_key        : 복사할 원본 이슈 키 (예: "SI-100")
        target_project    : 대상 프로젝트 키 (예: "OPS")
        summary_prefix    : 복사된 이슈 제목 앞에 추가할 텍스트
        summary_suffix    : 복사된 이슈 제목 뒤에 추가할 텍스트
        override_summary  : 제목을 완전히 다른 값으로 교체 (설정 시 prefix/suffix 무시)
        override_type     : 이슈 유형 변경 (미설정 시 원본과 동일)
        override_priority : 우선순위 변경
        override_assignee : 담당자 account_id 변경 ("" = 담당자 없음)
        override_due_date : 기한 변경 (YYYY-MM-DD)
        copy_labels       : 레이블 복사 여부 (기본 True)
        copy_description  : 설명 복사 여부 (기본 True)
        copy_comments     : 댓글 복사 여부 (기본 False)
        copy_subtasks     : 서브태스크 재귀 복사 여부 (기본 False)
        link_to_source    : 원본 이슈에 "복사됨(Clones)" 링크 생성 여부
        extra_fields      : 추가 커스텀 필드 딕셔너리

        Returns
        -------
        CopyResult : new_issue, source_issue, copied_comments, copied_subtasks 포함
        """
        self._logger.info(
            "COPY issue %s → project [%s]", source_key, target_project
        )

        # ── 1. 원본 이슈 상세 조회 ────────────────────────────────────────
        fields_to_fetch = [
            "summary", "description", "issuetype", "priority",
            "labels", "assignee", "duedate", "subtasks", "parent", "comment",
        ]
        src = self.get_issue(source_key, fields=fields_to_fetch)

        # ── 2. 제목 결정 ──────────────────────────────────────────────────
        if override_summary:
            new_summary = override_summary
        else:
            new_summary = f"{summary_prefix}{src.summary}{summary_suffix}"

        # ── 3. 새 이슈 필드 구성 ─────────────────────────────────────────
        new_issue = self.create_issue(
            project_key  = target_project,
            summary      = new_summary,
            issue_type   = override_type   or src.issue_type or "Task",
            description  = src.description if copy_description else "",
            assignee_id  = override_assignee if override_assignee != "" else
                           (src.assignee.account_id if not override_assignee == "" else ""),
            priority     = override_priority or src.priority,
            labels       = src.labels if copy_labels else [],
            due_date     = override_due_date or src.due_date,
            extra_fields = extra_fields,
        )
        self._logger.info("  Created: %s '%s'", new_issue.key, new_issue.summary)

        result = CopyResult(source=src, new_issue=new_issue)

        # ── 4. 댓글 복사 ─────────────────────────────────────────────────
        if copy_comments and src.comments:
            self._logger.info("  Copying %d comment(s)...", len(src.comments))
            for c in src.comments:
                header = f"[원본 댓글 | {c.author} | {c.created}]\n"
                self.add_comment(new_issue.key, header + c.body)
                result.copied_comments += 1

        # ── 5. 원본 이슈에 링크 추가 ─────────────────────────────────────
        if link_to_source:
            try:
                self._create_issue_link("Clones", new_issue.key, source_key)
                self._logger.info(
                    "  Linked: %s Clones %s", new_issue.key, source_key
                )
            except JiraApiError as e:
                # 링크 실패는 치명적이지 않으므로 경고만
                self._logger.warning("  Link failed (non-fatal): %s", e)

        # ── 6. 서브태스크 재귀 복사 ───────────────────────────────────────
        if copy_subtasks and src.subtasks:
            self._logger.info("  Copying %d subtask(s)...", len(src.subtasks))
            for sub_key in src.subtasks:
                try:
                    sub_result = self.copy_issue(
                        source_key       = sub_key,
                        target_project   = target_project,
                        copy_labels      = copy_labels,
                        copy_description = copy_description,
                        copy_comments    = copy_comments,
                        copy_subtasks    = False,    # 재귀 무한 방지
                        link_to_source   = link_to_source,
                    )
                    result.copied_subtasks.append(sub_result.new_issue.key)
                    self._logger.info(
                        "    Subtask copied: %s → %s", sub_key, sub_result.new_issue.key
                    )
                except JiraApiError as e:
                    self._logger.warning(
                        "    Subtask %s copy failed: %s", sub_key, e
                    )

        return result

    def _create_issue_link(
        self,
        link_type: str,
        inward_key: str,
        outward_key: str,
    ) -> None:
        """두 이슈 사이에 링크를 생성합니다."""
        body = {
            "type": {"name": link_type},
            "inwardIssue":  {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        }
        self._api.post("issueLink", json=body)

    # ── 연결 확인 ────────────────────────────────────────────────────────────

    def ping(self) -> dict:
        """JIRA 서버 연결 상태를 확인합니다."""
        self._logger.info("PING JIRA server")
        return self._api.get("serverInfo")

    # ── 내부 메서드 ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_auth(
        auth_type: str,
        email: str,
        api_token: str,
        username: str,
        password: str,
        pat: str,
    ) -> Any:
        at = auth_type.lower()
        if at == "token":
            return HTTPBasicAuth(email, api_token)
        elif at == "pat":
            return TokenAuth(pat)
        elif at == "basic":
            return HTTPBasicAuth(username, password)
        else:
            raise ValueError(f"Unsupported auth_type: {auth_type!r}")

    @staticmethod
    def _find_transition_id(
        transitions: list[JiraTransition],
        target: str,
        alias_map: dict[str, list[str]],
    ) -> str | None:
        """
        전환 이름 또는 별칭으로 transition id 를 찾습니다.
        대소문자 무시.
        """
        target_lower = target.lower()

        # 1) 직접 이름 매칭
        for t in transitions:
            if t.name.lower() == target_lower or t.to_status.lower() == target_lower:
                return t.id

        # 2) config 별칭 매칭
        aliases: list[str] = alias_map.get(target_lower, [])
        for alias in aliases:
            for t in transitions:
                if t.name.lower() == alias.lower() or t.to_status.lower() == alias.lower():
                    return t.id

        # 3) 부분 매칭 (fallback)
        for t in transitions:
            if (target_lower in t.name.lower() or
                    target_lower in t.to_status.lower()):
                return t.id

        return None
