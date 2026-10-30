import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from could_you.agent import Agent
from could_you.config import Config, DialogueProps, LLMProps
from could_you.cy_error import CYError, FaultOwner
from could_you.dialogue import Dialogue
from could_you.message import Message, TextContent, ToolUse
from could_you.subagent_jobs import SubagentJobs
from could_you.tools.call_could_you_tool import CallCouldYouTool
from could_you.tools.poll_could_you_tool import PollCouldYouTool


def result_json(result):
    return json.loads(result.tool_result.content[0].text)


@pytest.mark.asyncio
async def test_async_call_poll_and_descendant_shares_registry(tmp_path):
    class Session:
        def __init__(self):
            self.config = Config(llm=LLMProps(provider="openai"), dialogue=DialogueProps(load=False, store=False))

        def dialogue(self):
            return Dialogue(tmp_path, props=self.config.dialogue)

    manager = AsyncMock()
    manager.load_session = lambda _name: Session()
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

    with (
        patch("could_you.agent.Agent.__aenter__", new=enter),
        patch("could_you.agent.Agent.orchestrate", new=orchestrate),
        Dialogue(tmp_path, props=DialogueProps(load=False, store=False)) as dialogue,
    ):
        root = Agent(session_manager=manager, config=Session().config, dialogue=dialogue)
        call = CallCouldYouTool(manager, root.jobs)
        poll_tool = PollCouldYouTool(root.jobs)
        response = await call(
            ToolUse(toolUseId="call_1", name=call.name, input={}),
            {"dialogue_name": "test", "message": "go", "async": True},
        )
        job_id = result_json(response)["job_id"]
        poll_use = ToolUse(toolUseId="poll_1", name=poll_tool.name, input={})
        assert result_json(await poll_tool(poll_use, {"job_id": job_id})) == {"status": "pending"}
        await entered.wait()
        assert descendants[0].jobs is root.jobs
        assert not descendants[0].owns_jobs
        gate.set()
        assert await root.jobs.tasks[job_id] == "ready"
        assert result_json(await poll_tool(poll_use, {"job_id": job_id})) == {"status": "succeeded", "text": "ready"}
        await root.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_poll_tool_reports_failures_and_rejects_unknown_ids(tmp_path):
    config = Config(llm=LLMProps(provider="openai"))
    with Dialogue(tmp_path, props=DialogueProps(load=False, store=False)) as dialogue:
        agent = Agent(session_manager=AsyncMock(), config=config, dialogue=dialogue)
        poll_tool = PollCouldYouTool(agent.jobs)
        use = ToolUse(toolUseId="poll_1", name=poll_tool.name, input={})

        async def fail():
            raise ValueError("broken")

        job_id = agent.jobs.start(fail())
        await asyncio.sleep(0)
        assert result_json(await poll_tool(use, {"job_id": job_id})) == {"status": "failed", "error": "broken"}
        with pytest.raises(CYError, match="Unknown sub-agent job id") as exc:
            await poll_tool(use, {"job_id": "missing"})
        assert exc.value.fault_owner is FaultOwner.LLM
        await agent.jobs.close()


@pytest.mark.asyncio
async def test_root_exit_cancels_and_awaits_descendant_jobs(tmp_path):
    with Dialogue(tmp_path, props=DialogueProps(load=False, store=False)) as dialogue:
        root = Agent(session_manager=AsyncMock(), config=Config(llm=LLMProps(provider="openai")), dialogue=dialogue)
        child = Agent(session_manager=root.session_manager, config=root.config, dialogue=dialogue, jobs=root.jobs)
        started = asyncio.Event()
        finished = asyncio.Event()

        async def work():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                finished.set()

        job_id = child.jobs.start(work())
        await started.wait()
        await child.__aexit__(None, None, None)
        assert not finished.is_set()
        await root.__aexit__(None, None, None)
        assert finished.is_set()
        assert root.jobs.poll(job_id) == {"status": "failed", "error": "Sub-agent job was cancelled"}
        assert root.jobs.closed


@pytest.mark.asyncio
async def test_closed_registry_rejects_new_jobs_without_unawaited_coroutines():
    jobs = SubagentJobs()
    await jobs.close()

    async def work():
        return "unexpected"

    with pytest.raises(CYError, match="closing"):
        jobs.start(work())
