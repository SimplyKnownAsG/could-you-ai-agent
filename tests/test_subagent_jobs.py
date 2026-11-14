import asyncio
import json
from unittest.mock import patch

import pytest

from could_you.agent import Agent
from could_you.config import Config, DialogueProps, LLMProps, SubagentProps
from could_you.cy_error import CYError
from could_you.message import Message, TextContent, ToolUse
from could_you.session import Session, SessionManager
from could_you.tools.subagent_tools import CallSubagentTool, PollSubagentTool, SubagentServer


def result_json(result):
    return json.loads(result.tool_result.content[0].text)


def result_text(result):
    return result.tool_result.content[0].text


@pytest.mark.asyncio
async def test_async_call_poll_and_descendant_shares_registry(tmp_path):
    config_dir = tmp_path / ".could-you"
    config_dir.mkdir()

    gate = asyncio.Event()
    entered = asyncio.Event()
    descendants = []

    async def enter(agent):
        descendants.append(agent)
        entered.set()
        return agent

    async def orchestrate(agent, _query):
        await gate.wait()
        agent.dialogue.add(Message(role="assistant", content=[TextContent(text="ready")]))

    async with (
        SessionManager(cache_path=tmp_path) as manager,
        Session(
            config_dir,
            None,
            Config(llm=LLMProps(provider="openai"), dialogue=DialogueProps(load=False, store=False)),
        ) as session,
    ):
        child = Session(config_dir, None, session.config, depth=1)

        def load_session(_name, override, *, depth):
            assert depth == 1
            override(child.config)
            return child

        with (
            patch.object(manager, "load_session", side_effect=load_session),
            patch("could_you.agent.Agent.__aenter__", new=enter),
            patch("could_you.agent.Agent.orchestrate", new=orchestrate),
        ):
            root = Agent(session_manager=manager, session=session)
            call = CallSubagentTool(session.subagent_server, manager)
            poll_tool = PollSubagentTool(session.subagent_server)
            response = await call(
                ToolUse(toolUseId="call_1", name=call.name, input={}),
                {"dialogue_name": "test", "message": "go", "async": True},
            )
            job_id = result_json(response)["job_id"]
            poll_use = ToolUse(toolUseId="poll_1", name=poll_tool.name, input={})
            assert result_text(await poll_tool(poll_use, {"job_id": job_id})) == "status: pending"
            await entered.wait()
            assert descendants[0].session_manager is root.session_manager
            assert descendants[0].session is child
            assert child.depth == 1
            assert child.subagent_server is not session.subagent_server
            gate.set()
            assert await session.subagent_server.tasks[job_id] == "ready"
            assert result_text(await poll_tool(poll_use, {"job_id": job_id})) == "status: success\n\nready"


@pytest.mark.asyncio
async def test_poll_tool_reports_failures_and_unknown_ids(tmp_path):
    async with (
        SessionManager(cache_path=tmp_path),
        Session(
            tmp_path,
            None,
            Config(llm=LLMProps(provider="openai"), dialogue=DialogueProps(load=False, store=False)),
        ) as session,
    ):
        poll_tool = PollSubagentTool(session.subagent_server)
        use = ToolUse(toolUseId="poll_1", name=poll_tool.name, input={})

        async def fail():
            raise ValueError("broken")

        job_id = session.subagent_server.start(fail())
        await asyncio.sleep(0)
        assert result_text(await poll_tool(use, {"job_id": job_id})) == "status: failed\nerror: broken"
        assert result_text(await poll_tool(use, {"job_id": "missing"})) == (
            "status: failed\nerror: Unknown sub-agent job id: missing"
        )


@pytest.mark.asyncio
async def test_manager_exit_cancels_and_awaits_descendant_jobs(tmp_path):
    started = asyncio.Event()
    finished = asyncio.Event()

    async def work():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            finished.set()

    async with (
        SessionManager(cache_path=tmp_path) as manager,
        Session(tmp_path, None, Config(llm=LLMProps(provider="openai"))) as session,
    ):
        root = Agent(session_manager=manager, session=session)
        child = Agent(session_manager=manager, session=session)
        job_id = child.session.subagent_server.start(work())
        await started.wait()
        await child.__aexit__(None, None, None)
        assert not finished.is_set()
        await root.__aexit__(None, None, None)
        assert not finished.is_set()
    assert finished.is_set()
    assert session.subagent_server.poll(job_id) == "status: failed\nerror: Sub-agent job was cancelled"
    assert session.subagent_server.closed


@pytest.mark.asyncio
async def test_closed_registry_rejects_new_jobs_without_unawaited_coroutines():
    jobs = SubagentServer(SubagentProps(), 0)
    await jobs.close()

    async def work():
        return "unexpected"

    with pytest.raises(CYError, match="closing"):
        jobs.start(work())
