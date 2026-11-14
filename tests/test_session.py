import asyncio
from unittest.mock import mock_open, patch

import pytest

from could_you.config import Config
from could_you.session import Session, SessionManager


def test_session_workspace_is_config_directory_parent(tmp_path):
    session = Session(tmp_path / ".could-you", None, Config(llm={}))
    assert session.workspace_dir == tmp_path


@pytest.mark.asyncio
async def test_enter_exit_loads_and_saves_sessions():
    sessions_dict = {"/project/root": {}}
    m = mock_open(read_data='{"/project/root": {}}')
    with (
        patch("builtins.open", m),
        patch("os.path.exists", return_value=True),
        patch("json.load", return_value=sessions_dict),
        patch("json.dump") as mock_dump,
    ):
        async with SessionManager() as mgr:
            assert mgr.sessions == sessions_dict
        mock_dump.assert_called_once_with(sessions_dict, m(), indent=2)


@pytest.mark.asyncio
async def test_session_exit_cancels_jobs_even_if_dialogue_close_fails(tmp_path):
    started = asyncio.Event()
    finished = asyncio.Event()

    async def work():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            finished.set()

    session = Session(tmp_path, None, Config(llm={}))

    async def run_session():
        async with session:
            session.subagent_server.start(work())
            await started.wait()

    with (
        patch.object(session.dialogue, "__exit__", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        await run_session()

    assert finished.is_set()
    assert session.subagent_server.closed


# def test_init_session_creates_new_session_and_calls_init():
#     dummy_config = DummyConfig("/test/root")
#     with patch("could_you.session.init", return_value=dummy_config) as mock_init:
#         mgr = SessionManager()
#         mgr.sessions = {}
#         config = mgr.init_session()
#         mock_init.assert_called_once()
#         assert mgr.sessions["/test/root"] == {}
#         assert config is dummy_config


# def test_load_session_loads_config_and_sets_session():
#     dummy_config = DummyConfig("/another/root"), Path("/another/root/.could-you")
#     with patch("could_you.session.load", return_value=dummy_config) as mock_load:
#         mgr = SessionManager()
#         mgr.sessions = {}
#         config = mgr.load_session(None)
#         mock_load.assert_called_once()
#         assert mgr.sessions["/another/root"] == {}
#         assert config is dummy_config


def test_list_logs_all_session_roots():
    mgr = SessionManager()
    mgr.sessions = {"/foo": {}, "/bar": {}}
    with patch("could_you.session.LOGGER") as mock_logger:
        mgr.list()
        assert mock_logger.info.call_count == 2
        calls = [call.args[0] for call in mock_logger.info.call_args_list]
        assert "Session root: /foo" in calls
        assert "Session root: /bar" in calls
