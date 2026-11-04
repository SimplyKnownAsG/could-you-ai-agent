"""
Run Bash in srt (@anthropic-ai/sandbox-runtime).
"""

import asyncio
import math
import os
import signal
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Any

from mcp import Tool

from could_you.logging_config import LOGGER
from could_you.session import Session

from ..config import MCPServerProps
from ..cy_error import CYError, FaultOwner
from ..mcp_server import MCPServer, MCPTool
from ..message import ToolResult, ToolResultContent, ToolResultInnerTextContent, ToolUse

MAX_OUTPUT_BYTES = 64_000


class RunBashTool(MCPTool):
    def __init__(self, session: Session):
        super().__init__(
            MCPServer(name="__self__", props=MCPServerProps(command="echo")),
            Tool(
                name="__run_bash__",
                description=(
                    "Run Bash in an isolated Linux bubblewrap container with no network. "
                    "The workspace is writable; commands can read its contents, including secrets. "
                    "No execution confirmation."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Bash command; pipes and shell operators are supported",
                        },
                        "timeout": {"type": "number", "description": "Seconds (default 30)"},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            ),
            enabled=session.config.tools.bash.enable and is_srt_executable(),
        )
        self.session = session

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]) -> ToolResultContent:
        if not isinstance(tool_args, dict) or set(tool_args) - {"command", "timeout"}:
            raise CYError(
                message="__run_bash__ expects command and optional timeout", retriable=False, fault_owner=FaultOwner.LLM
            )

        command = tool_args.get("command")
        seconds = tool_args.get("timeout", 30)
        if not isinstance(command, str) or not command.strip():
            raise CYError(
                message="__run_bash__ expects a nonempty command", retriable=False, fault_owner=FaultOwner.LLM
            )
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or not seconds > 0
        ):
            raise CYError(
                message="__run_bash__ timeout must be a positive finite number",
                retriable=False,
                fault_owner=FaultOwner.LLM,
            )

        text, status = await self._run(command, seconds)
        return ToolResultContent(
            toolResult=ToolResult(
                toolUseId=tool_use.tool_use_id,
                content=[ToolResultInnerTextContent(text=text)],
                status=status,
            )
        )

    async def _run(self, command: str, seconds: float) -> tuple[str, str]:
        args = ["srt"]

        if srt_settings := self.session.config.tools.bash.srt_settings:
            args.extend(["--settings", Path(srt_settings).resolve()])

        args.extend(["-c", command])

        try:
            process = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True
            )
        except OSError as exc:
            return f"Failed to start sandbox: {exc}", "error"

        try:
            output, _ = await asyncio.wait_for(process.communicate(), seconds)
        except (TimeoutError, asyncio.CancelledError) as exc:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.communicate()
            if isinstance(exc, asyncio.CancelledError):
                raise
            return f"Command timed out after {seconds:g} seconds", "error"

        truncated = len(output) > MAX_OUTPUT_BYTES
        text = output[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")

        if truncated:
            text += "\n[output truncated]"

        text += f"\n[exit code: {process.returncode}]"
        return text, "success" if process.returncode == 0 else "error"


def is_srt_executable():
    try:
        # Runs the binary with a safe fallback flag; captures output to keep terminal clean
        version = subprocess.check_output(
            ["srt", "--version"],  # noqa : S607
        )
        LOGGER.info(f"BashTool: Found srt {version.strip()}")
        return True  # noqa: TRY300
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError):
        # FileNotFoundError: 'srt' is missing from PATH entirely
        # PermissionError: 'srt' exists but the system blocks execution
        LOGGER.warning(
            "Bash disabled, could not find srt executable install with `npm install -g @anthropic-ai/sandbox-runtime`"
        )
        return False
