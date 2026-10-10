"""Small streamable-HTTP client for the official McDonald's MCP."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "https://mcp.mcd.cn"


class McpError(RuntimeError):
    pass


class McdMcp:
    def __init__(self, token: str, url: str = DEFAULT_URL, timeout: float = 45) -> None:
        if not token or not token.strip():
            raise McpError("缺少 MCP Token。放到环境变量 MCD_MCP_TOKEN，不要写进仓库。")
        self._token = token.strip()
        self._url = url
        self._timeout = timeout
        self._session_id = ""
        self._next_id = 0

    def initialize(self) -> Any:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcd-office-lunch", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        return result

    def tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return unwrap_tool(result)

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        self._next_id += 1
        message = self._post(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        )
        if not isinstance(message, dict):
            raise McpError(f"{method} 没有返回 JSON")
        if message.get("error"):
            detail = message["error"].get("message") if isinstance(message["error"], dict) else message["error"]
            raise McpError(str(detail))
        return message.get("result")

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        try:
            self._post({"jsonrpc": "2.0", "method": method, "params": params})
        except McpError:
            return

    def _post(self, payload: dict[str, Any]) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._token}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(self._url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self._session_id = session
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise McpError(f"MCP HTTP {exc.code}：{detail}") from None
        except urllib.error.URLError as exc:
            raise McpError(f"连不上 MCP：{exc.reason}") from None
        if not raw.strip():
            return None
        return parse_message(raw)


def parse_message(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    messages = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if not body or body == "[DONE]":
            continue
        messages.append(json.loads(body))
    if not messages:
        raise McpError("MCP 响应里没有 JSON")
    return messages[-1]


def unwrap_tool(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    if result.get("isError"):
        raise McpError(_text_blocks(result) or "工具调用失败")
    text = _text_blocks(result)
    if not text:
        return result
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


def _text_blocks(result: dict[str, Any]) -> str:
    blocks = result.get("content")
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts).strip()


def walk_records(payload: Any, marker: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if marker in node and node.get(marker) not in (None, ""):
                found.append(node)
                return
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return found


def find_fen(payload: Any, keys: tuple[str, ...]) -> int | None:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload and isinstance(payload[key], (int, float)) and not isinstance(payload[key], bool):
                return int(round(float(payload[key])))
        for value in payload.values():
            found = find_fen(value, keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_fen(value, keys)
            if found is not None:
                return found
    return None
