import pytest
from pathlib import Path

from .dir_changer import DirChanger

@pytest.fixture
def tmp_dir(tmp_path: Path):
    dir_changer = DirChanger(tmp_path)
    dir_changer.open()
    yield tmp_path
    dir_changer.close()
