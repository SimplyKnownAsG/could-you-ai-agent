# The function we will create in `could_you/memory/search.py`
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from could_you.memory.search import _parse_git_grep_output, search_memory

# A hardcoded sample of `git grep` output.
# This includes a file with one match and a file with multiple matches.
# It uses the `--line-number` and `--all-match` flags.
# git grep -i --line-number --all-match -e "memory" -e "search"
SAMPLE_GIT_GREP_OUTPUT = """
.could-you/MEMORY.md:123:This is a line about memory search.
.could-you/archive/123.dialogue.json:10:{"role": "user", "content": "Can you search my memory?"}
.could-you/archive/123.dialogue.json:11:{"role": "assistant", "content": "Yes, I can search my memory."}
"""


def test_parse_git_grep_output_with_sample_data():
    """
    Tests that the parser correctly transforms a sample `git grep` output string
    into the desired structured dictionary.
    """
    # This is the structure we want to get from the parser.
    # It's a dictionary where keys are file paths and values are lists of
    # tuples, with each tuple containing a line number and the line content.
    expected = {
        ".could-you/MEMORY.md": [(123, "This is a line about memory search.")],
        ".could-you/archive/123.dialogue.json": [
            (10, {"role": "user", "content": "Can you search my memory?"}),
            (11, {"role": "assistant", "content": "Yes, I can search my memory."}),
        ],
    }

    # The test `test_parse_git_grep_output_with_sample_data` will fail until this
    # function is implemented correctly.
    actual = _parse_git_grep_output(SAMPLE_GIT_GREP_OUTPUT)

    assert actual == expected


def test_search_memory_unit(tmp_path: Path):
    """
    Tests the search_memory function directly, bypassing the CLI.
    """
    # 1. Setup: Create a temporary could-you environment and archive file
    could_you_dir = tmp_path / ".could-you"
    conversations_dir = could_you_dir / "conversations"
    conversations_dir.mkdir(parents=True)

    # Initialize a git repository in the temporary directory
    subprocess.run(["git", "init"], cwd=str(could_you_dir), check=True)

    # Create the other memory files that are searched by default
    (could_you_dir / "FORMATIVE.md").touch()
    (could_you_dir / "MEMORY.md").touch()
    (could_you_dir / "TODO.md").touch()

    archive_content = """{"role": "user", "content": "This is a test message with a unique search term: xyz_super_unique_term_123"}\n"""
    archive_file = conversations_dir / "test_archive.jsonl"
    archive_file.write_text(archive_content)

    # Add the file to the git index
    subprocess.run(["git", "add", str(archive_file)], cwd=str(could_you_dir), check=True)

    # Mock the config and config loading
    mock_config = MagicMock()
    mock_config.could_you_dir = could_you_dir

    # 2. Execute: Call the search_memory function
    search_terms = ["xyz_super_unique_term_123"]
    results = search_memory(search_terms, cwd=str(could_you_dir))

    # 3. Assert: Check for the expected output
    assert results is not None
    assert len(results) == 1

    # The key is the file path
    file_path = next(iter(results.keys()))
    assert file_path == str(archive_file.relative_to(could_you_dir))

    # The value is a list of tuples (line_number, content)
    search_hits = next(iter(results.values()))
    assert len(search_hits) == 1

    line_num, content = search_hits[0]
    assert line_num == 1
    assert isinstance(content, dict)
    assert "This is a test message" in content.get("content", "")
