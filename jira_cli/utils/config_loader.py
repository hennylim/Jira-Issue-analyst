"""
utils/config_loader.py
----------------------
YAML 기반 외부 설정 파일 로더.
환경변수 오버라이드 지원.
"""

import os
from pathlib import Path
from typing import Any

import yaml


# 환경변수 → config 경로 매핑
_ENV_OVERRIDES: dict[str, str] = {
    "JIRA_BASE_URL":   "jira.base_url",
    "JIRA_EMAIL":      "jira.email",
    "JIRA_API_TOKEN":  "jira.api_token",
    "JIRA_PAT":        "jira.pat",
    "JIRA_API_VERSION":"jira.api_version",
}

# 기본 config 검색 순서
_DEFAULT_PATHS = [
    "config.yaml",
    "config.yml",
    os.path.expanduser("~/.jira_cli/config.yaml"),
    "/etc/jira_cli/config.yaml",
]


def _set_nested(d: dict, key_path: str, value: Any) -> None:
    """점(.) 구분 경로로 중첩 딕셔너리 값을 설정합니다."""
    keys = key_path.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _get_nested(d: dict, key_path: str, default: Any = None) -> Any:
    """점(.) 구분 경로로 중첩 딕셔너리 값을 조회합니다."""
    keys = key_path.split(".")
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


class ConfigLoader:
    """
    JIRA CLI 설정 로더.

    우선순위: 환경변수 > 지정 config 파일 > 기본 경로 config 파일 > 기본값

    Usage
    -----
    cfg = ConfigLoader("config.yaml")
    base_url = cfg.get("jira.base_url")
    """

    def __init__(self, config_path: str | None = None):
        self._data: dict = {}
        self._path: str = ""
        self._load(config_path)
        self._apply_env_overrides()

    # ── 공개 메서드 ──────────────────────────────────────────────────────────

    def get(self, key_path: str, default: Any = None) -> Any:
        """점(.) 구분 키로 설정값을 반환합니다."""
        return _get_nested(self._data, key_path, default)

    def get_section(self, section: str) -> dict:
        """최상위 섹션 전체를 딕셔너리로 반환합니다."""
        return self._data.get(section, {})

    def set(self, key_path: str, value: Any) -> None:
        """런타임에 설정값을 동적으로 변경합니다."""
        _set_nested(self._data, key_path, value)

    @property
    def config_path(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"ConfigLoader(path={self._path!r})"

    # ── 내부 메서드 ──────────────────────────────────────────────────────────

    def _load(self, config_path: str | None) -> None:
        candidates = (
            [config_path] if config_path else []
        ) + _DEFAULT_PATHS

        for path in candidates:
            if path and Path(path).is_file():
                with open(path, "r", encoding="utf-8") as f:
                    self._data = yaml.safe_load(f) or {}
                self._path = str(Path(path).resolve())
                return

        # 파일 없으면 빈 설정으로 시작
        self._data = {}
        self._path = "(none)"

    def _apply_env_overrides(self) -> None:
        """환경변수로 config 값을 덮어씁니다."""
        for env_key, cfg_path in _ENV_OVERRIDES.items():
            val = os.environ.get(env_key)
            if val:
                _set_nested(self._data, cfg_path, val)
