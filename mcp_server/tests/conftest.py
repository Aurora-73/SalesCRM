"""MCP 测试共享 fixture。"""
import asyncio

import pytest


@pytest.fixture(scope="module")
def tools():
    """加载 MCP 服务器注册的所有工具，供多个测试复用。"""
    from mcp_server.server import mcp
    return asyncio.run(mcp.list_tools())
