from pathlib import Path

import pytest

from .dir_changer import DirChanger


@pytest.fixture
def tmp_dir(tmp_path: Path):
    dir_changer = DirChanger(tmp_path)
    dir_changer.open()
    yield tmp_path
    dir_changer.close()


@pytest.fixture
def tmp_cy_config_dir(tmp_path, monkeypatch):
    tmp_xdg_config_home = tmp_path.with_stem(tmp_path.stem + "xdg")
    tmp_xdg_config_home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_xdg_config_home))
    tmp_cy_config_dir = tmp_xdg_config_home / "could-you"
    tmp_cy_config_dir.mkdir()
    return tmp_cy_config_dir
