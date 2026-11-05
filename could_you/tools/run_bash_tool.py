"""
Run Bash in srt (@anthropic-ai/sandbox-runtime).
"""

import asyncio
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
                    "No execution confirmation. Use .could-you.tmp/ for temp work"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Bash command; pipes and shell operators are supported",
                        },
                        "timeout": {
                            "type": "number",
                            "description": f"Seconds (default: {session.config.tools.bash.default_timeout}, max: {session.config.tools.bash.max_timeout})",
                        },
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            ),
            enabled=session.config.tools.bash.enable and is_srt_executable(),
        )
        self.session = session
        self._made_temp = False

    async def __call__(self, tool_use: ToolUse, tool_args: dict[str, Any]) -> ToolResultContent:
        if not isinstance(tool_args, dict) or set(tool_args) - {"command", "timeout"}:
            raise CYError(
                message="__run_bash__ expects command and optional timeout", retriable=False, fault_owner=FaultOwner.LLM
            )

        command = tool_args.get("command")
        raw_timeout = tool_args.get("timeout", self.session.config.tools.bash.default_timeout)

        try:
            timeout = int(float(raw_timeout))

            if timeout > self.session.config.tools.bash.max_timeout:
                timeout = self.session.config.tools.bash.max_timeout
                LOGGER.warning(f'__run_bash__ provided timeout "{raw_timeout}" overriden to use max "{timeout}"')
            elif timeout <= 0:
                timeout = self.session.config.tools.bash.default_timeout
                LOGGER.warning(f'__run_bash__ provided timeout "{raw_timeout}" overriden to use max "{timeout}"')
        except Exception as ex:
            timeout = self.session.config.tools.bash.default_timeout
            LOGGER.warning(f'__run_bash__ could not cast "{raw_timeout}" to int: {ex!s}, using default: {timeout}')

        if not isinstance(command, str) or not command.strip():
            raise CYError(
                message="__run_bash__ expects a nonempty command", retriable=False, fault_owner=FaultOwner.LLM
            )

        text, status = await self._run(command, timeout)
        return ToolResultContent(
            toolResult=ToolResult(
                toolUseId=tool_use.tool_use_id,
                content=[ToolResultInnerTextContent(text=text)],
                status=status,
            )
        )

    async def _run(self, command: str, seconds: float) -> tuple[str, str]:
        if not self._made_temp:
            (self.session.workspace / ".could-you.tmp").mkdir()
            self._made_temp = True

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
