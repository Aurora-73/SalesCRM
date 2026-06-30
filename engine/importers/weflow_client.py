"""WeFlow HTTP API 客户端"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class WeFlowError(Exception):
    pass


class WeFlowAuthError(WeFlowError):
    pass


class WeFlowClient:

    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{self.base_url}{path}"
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered)

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise WeFlowAuthError(
                    "WeFlow API 认证失败 (HTTP 401)"
                ) from e
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise WeFlowError(f"HTTP {e.code}: {body_text}") from e
        except urllib.error.URLError as e:
            raise WeFlowError(f"连接 WeFlow API 失败: {e.reason}") from e

    def health(self) -> bool:
        try:
            self._get("/api/v1/health")
            return True
        except WeFlowError:
            return False

    def list_contacts(
        self, keyword: str | None = None, limit: int = 100
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if keyword:
            params["keyword"] = keyword
        resp = self._get("/api/v1/contacts", params=params)
        return resp.get("contacts", [])

    def list_sessions(
        self, keyword: str | None = None, limit: int = 100
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if keyword:
            params["keyword"] = keyword
        resp = self._get("/api/v1/sessions", params=params)
        return resp.get("sessions", [])

    def pull_messages(
        self, session_id: str, since: int = 0, limit: int = 5000
    ) -> tuple[list[dict], int, bool]:
        path = f"/api/v1/sessions/{urllib.parse.quote(session_id, safe='')}/messages"
        params: dict[str, Any] = {"limit": limit}
        if since > 0:
            params["since"] = since

        resp = self._get(path, params=params)

        messages = resp.get("messages", [])
        sync = resp.get("sync", {})
        watermark = sync.get("watermark", since)
        has_more = sync.get("hasMore", False)

        return messages, watermark, has_more

    def get_messages(
        self,
        talker: str,
        limit: int = 1000,
        offset: int = 0,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        """GET /api/v1/messages → { success, talker, count, hasMore, messages }

        原始 JSON 格式。注意：不传 start/end 时 WeFlow 可能返回 0 条，
        建议始终传入日期范围。
        """
        params: dict[str, Any] = {
            "talker": talker,
            "limit": limit,
        }
        if offset > 0:
            params["offset"] = offset
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        return self._get("/api/v1/messages", params=params)

    def get_moments_timeline(
        self,
        limit: int = 20,
        offset: int = 0,
        usernames: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if offset > 0:
            params["offset"] = offset
        if usernames:
            params["usernames"] = usernames
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        return self._get("/api/v1/sns/timeline", params=params)

    def get_media_url(self, relative_path: str) -> str:
        return f"{self.base_url}/api/v1/media/{relative_path}"

    def download_media(self, relative_path: str, save_path: str) -> bool:
        url = self.get_media_url(relative_path)
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                with open(save_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            return True
        except Exception as e:
            logger.warning(f"下载媒体失败 {relative_path}: {e}")
            return False
