import shutil
from unittest.mock import AsyncMock, patch

import pytest

from could_you.config import Config
from could_you.cy_error import CYError
from could_you.message import ToolUse
from could_you.session import Session
from could_you.tools.run_bash_tool import RunBashTool


def tool_use():
    return ToolUse(name="__run_bash__", input={}, toolUseId="call_1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"command": " "},
    ],
)
async def test_invalid_arguments_do_not_execute(tmp_path, arguments):
    if not shutil.which("srt"):
        pytest.skip("srt is not installed")

    async with Session(tmp_path, None, Config(llm={})) as session:
        tool = RunBashTool(session)
        with patch.object(tool, "_run", new_callable=AsyncMock) as run:
            with pytest.raises(CYError):
                await tool(tool_use(), arguments)
            run.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [(True, 1), (-1, 60), ("0", 60), (float("inf"), 60)],
)
async def test_timeout_default(tmp_path, arguments):
    if not shutil.which("srt"):
        pytest.skip("srt is not installed")

    async with Session(tmp_path, None, Config(llm={})) as session:
        tool = RunBashTool(session)
        timeout, expected = arguments
        with patch.object(
            tool, "_run", new_callable=AsyncMock, return_value=("/home/borg/fun-stuff\n[exit code: 1]", "success")
        ) as run:
            await tool(tool_use(), {"command": "pwd", "timeout": timeout})
        run.assert_awaited_once_with("pwd", expected)


@pytest.mark.asyncio
async def test_result_status_and_timeout_are_forwarded(tmp_path):
    if not shutil.which("srt"):
        pytest.skip("srt is not installed")

    async with Session(tmp_path, None, Config(llm={})) as session:
        tool = RunBashTool(session)
        with patch.object(
            tool, "_run", new_callable=AsyncMock, return_value=("failed\n[exit code: 3]", "error")
        ) as run:
            result = await tool(tool_use(), {"command": "exit 3", "timeout": 4})
        run.assert_awaited_once_with("exit 3", 4)
        assert result.tool_result.status == "error"
        assert result.tool_result.content[0].text == "failed\n[exit code: 3]"
