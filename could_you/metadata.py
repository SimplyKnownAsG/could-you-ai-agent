from pathlib import Path

from attrs import define, field


@define(frozen=True)
class LoadedFileMetadata:
    directive: str
    path: str
    bytes: int

    @classmethod
    def from_path(cls, *, directive: str, path: Path) -> "LoadedFileMetadata":
        resolved_path = path.resolve()
        return cls(directive=directive, path=str(resolved_path), bytes=resolved_path.stat().st_size)


@define(frozen=True)
class PromptMetadata:
    loaded_files: list[LoadedFileMetadata] = field(factory=list)

    @property
    def total_loaded_bytes(self) -> int:
        return sum(file.bytes for file in self.loaded_files)

    @property
    def loaded_file_count(self) -> int:
        return len(self.loaded_files)

    def has_directive(self, directive: str) -> bool:
        return any(file.directive == directive for file in self.loaded_files)
