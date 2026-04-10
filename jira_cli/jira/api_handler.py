"""
jira/api_handler.py
-------------------
JIRA REST API v2 / v3 자동 감지 및 요청 래퍼.
- Cloud: v3 (ADF body 형식)
- Server/Data Center: v2 (plain text body)
"""

from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import urljoin, urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import get_logger


# ── 상수 ──────────────────────────────────────────────────────────────────────
DETECT_PATH = "/rest/api/latest/serverInfo"
API_V2      = "2"
API_V3      = "3"


class JiraApiError(Exception):
    """JIRA API 호출 오류."""
    def __init__(self, message: str, status_code: int = 0, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response    = response or {}

    def __str__(self) -> str:
        return f"[HTTP {self.status_code}] {super().__str__()}"


class ApiHandler:
    """
    JIRA REST API 요청 핸들러.

    Parameters
    ----------
    base_url    : JIRA 서버 URL
    auth        : requests 인증 객체 (HTTPBasicAuth, TokenAuth 등)
    api_version : "auto" | "2" | "3"
    timeout     : 요청 타임아웃 (초)
    verify_ssl  : SSL 검증 여부
    max_retries : 재시도 횟수
    """

    def __init__(
        self,
        base_url: str,
        auth: Any,
        api_version: str = "auto",
        timeout: int = 30,
        verify_ssl: bool = True,
        max_retries: int = 3,
    ):
        self._base_url    = base_url.rstrip("/")
        self._auth        = auth
        self._timeout     = timeout
        self._verify_ssl  = verify_ssl
        self._logger      = get_logger("jira_cli.api")
        self._session     = self._build_session(max_retries)

        # API 버전 결정
        if api_version == "auto":
            self._api_version = self._detect_version()
        else:
            self._api_version = api_version

        self._logger.info("JIRA API version: v%s", self._api_version)

    # ── 공개 프로퍼티 ────────────────────────────────────────────────────────

    @property
    def api_version(self) -> str:
        return self._api_version

    @property
    def is_v3(self) -> bool:
        return self._api_version == API_V3

    def api_url(self, path: str) -> str:
        """API 경로를 포함한 전체 URL을 반환합니다."""
        base = f"{self._base_url}/rest/api/{self._api_version}"
        return f"{base}/{path.lstrip('/')}"

    # ── HTTP 메서드 ──────────────────────────────────────────────────────────

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None) -> dict:
        return self._request("POST", path, json=json)

    def put(self, path: str, json: dict | None = None) -> dict:
        return self._request("PUT", path, json=json)

    def delete(self, path: str) -> dict:
        return self._request("DELETE", path)

    def upload(self, path: str, files: dict, headers: dict | None = None) -> dict:
        """파일 업로드를 위한 multipart/form-data 요청 (JSON Content-Type 무시)."""
        url = self.api_url(path)
        # JIRA 첨부파일 API 등은 X-Atlassian-Token: no-check 가 필수인 경우가 많음
        req_headers = headers or {}
        # Accept는 json을 받기 위해 유지
        req_headers["Accept"] = "application/json"
        
        self._logger.debug("POST (upload) %s", url)
        start = time.monotonic()
        try:
            resp = self._session.request(
                "POST",
                url,
                auth=self._auth,
                files=files,
                timeout=self._timeout,
                verify=self._verify_ssl,
                headers=req_headers,
            )
            elapsed = time.monotonic() - start
            self._logger.debug(
                "POST (upload) %s → %d  (%.2fs)", url, resp.status_code, elapsed
            )

            if resp.status_code == 204 or not resp.text:
                return {}

            try:
                data = resp.json()
            except ValueError:
                data = {"raw": resp.text}

            if not resp.ok:
                error_msg = self._extract_error(data, resp.status_code)
                raise JiraApiError(error_msg, resp.status_code, data)
            
            # 배열 형식(v2 v3 attachment response)인 경우 dict로 감싸 반환
            if isinstance(data, list):
                return {"attachments": data}
            return data
            
        except JiraApiError:
            raise
        except requests.exceptions.ConnectionError as e:
            raise JiraApiError(f"Connection failed: {e}", 0)
        except requests.exceptions.Timeout:
            raise JiraApiError(f"Request timed out after {self._timeout}s", 408)
        except Exception as e:
            raise JiraApiError(f"Unexpected error: {e}", 0)

    # ── ADF 헬퍼 ────────────────────────────────────────────────────────────

    def make_body(self, text: str) -> Any:
        """
        API 버전에 맞는 body 형식을 반환합니다.
        v3: ADF(Atlassian Document Format) 객체
        v2: plain text string
        """
        if self.is_v3:
            return {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            }
        return text

    # ── 내부 메서드 ──────────────────────────────────────────────────────────

    def _detect_version(self) -> str:
        """서버 정보로 API 버전을 자동 감지합니다."""
        url = f"{self._base_url}{DETECT_PATH}"
        try:
            resp = self._session.get(
                url,
                auth=self._auth,
                timeout=self._timeout,
                verify=self._verify_ssl,
            )
            resp.raise_for_status()
            data = resp.json()
            # Cloud 는 "deploymentType": "Cloud", Server 는 없거나 "Server"
            deploy_type = data.get("deploymentType", "Server")
            version = API_V3 if deploy_type == "Cloud" else API_V2
            self._logger.debug(
                "Server: %s (%s) → API v%s",
                data.get("serverTitle", ""),
                deploy_type,
                version,
            )
            return version
        except Exception as e:
            self._logger.warning("API version auto-detect failed (%s). Falling back to v2.", e)
            return API_V2

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        url = self.api_url(path)
        self._logger.debug("%s %s  params=%s", method, url, params)

        start = time.monotonic()
        try:
            resp = self._session.request(
                method,
                url,
                auth=self._auth,
                params=params,
                json=json,
                timeout=self._timeout,
                verify=self._verify_ssl,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            elapsed = time.monotonic() - start
            self._logger.debug(
                "%s %s → %d  (%.2fs)", method, url, resp.status_code, elapsed
            )

            if resp.status_code == 204 or not resp.text:
                return {}

            try:
                data = resp.json()
            except ValueError:
                data = {"raw": resp.text}

            if not resp.ok:
                error_msg = self._extract_error(data, resp.status_code)
                raise JiraApiError(error_msg, resp.status_code, data)

            return data

        except JiraApiError:
            raise
        except requests.exceptions.ConnectionError as e:
            raise JiraApiError(f"Connection failed: {e}", 0)
        except requests.exceptions.Timeout:
            raise JiraApiError(f"Request timed out after {self._timeout}s", 408)
        except Exception as e:
            raise JiraApiError(f"Unexpected error: {e}", 0)

    def _build_session(self, max_retries: int) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @staticmethod
    def _extract_error(data: dict, status_code: int) -> str:
        if isinstance(data, dict):
            if "errorMessages" in data:
                msgs = data["errorMessages"]
                if msgs:
                    return " / ".join(msgs)
            if "errors" in data:
                errs = data["errors"]
                if isinstance(errs, dict):
                    return " / ".join(f"{k}: {v}" for k, v in errs.items())
            if "message" in data:
                return data["message"]
        return f"HTTP {status_code} error"
