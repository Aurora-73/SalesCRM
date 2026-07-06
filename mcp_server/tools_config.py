"""MCP 配置切换工具（无装饰器，由 server.py 注册）。"""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "system" / "config.yaml"


def _load_raw() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_raw(raw: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def get_backend() -> dict:
    """查看当前数据后端配置。"""
    try:
        raw = _load_raw()
        wf = raw.get("weflow", {})
        return {
            "backend": wf.get("backend", "wcd"),
            "base_url": wf.get("base_url", ""),
            "has_token": bool(wf.get("token")),
        }
    except Exception as e:
        return {"error": "CONFIG_READ_ERROR", "message": str(e)}


def set_backend(backend: str, base_url: str | None = None, token: str | None = None) -> dict:
    """切换数据后端（wcd 或 weflow），可选更新 base_url 和 token。"""
    valid = {"wcd", "weflow"}
    if backend not in valid:
        return {"error": "INVALID_BACKEND", "message": f"无效后端: {backend}，可选: {', '.join(sorted(valid))}"}
    try:
        raw = _load_raw()
        if "weflow" not in raw:
            raw["weflow"] = {}
        raw["weflow"]["backend"] = backend
        if base_url is not None:
            raw["weflow"]["base_url"] = base_url
        if token is not None:
            raw["weflow"]["token"] = token
        _save_raw(raw)
        return {"success": True, "message": f"后端已切换为 {backend}"}
    except Exception as e:
        return {"error": "CONFIG_WRITE_ERROR", "message": str(e), "suggestion": "检查 config.yaml 是否可写"}
