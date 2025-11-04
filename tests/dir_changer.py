import os
from pathlib import Path


class DirChanger:
    def __init__(self, path: Path):
        self.new_path = path
        self.original = None

    def __enter__(self):
        self.open()
        return self

    def open(self):
        self.original = Path.cwd()
        os.chdir(self.new_path)

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self.original:
            os.chdir(self.original)
