# This module will contain the core logic for the `cy --search-memory` command.
import json
import subprocess

from ..logging_config import LOGGER

# The expected number of parts from splitting a `git grep` output line.
# Format: <file_path>:<line_number>:<content>
_GIT_GREP_LINE_PARTS = 3

# The files and directories to search within the .could-you directory.
# We explicitly exclude the live dialogue.json as per the plan.
SEARCH_PATHS = [
    "FORMATIVE.md",
    "MEMORY.md",
    "TODO.md",
    "workspaces/*/conversations/*.dialogue.json",
]


def _parse_git_grep_output(output: str) -> dict[str, list[tuple[int, str | dict]]]:
    """
    Parses the raw output from a `git grep` command into a structured dictionary.
    """
    results: dict[str, list[tuple[int, str | dict]]] = {}
    for line in output.strip().splitlines():
        if not line:
            continue
        try:
            parts = line.split(":", 2)
            if len(parts) < _GIT_GREP_LINE_PARTS:
                continue  # Skip malformed lines
            file_path, line_num_str, content_str = parts
            line_num = int(line_num_str)

            if file_path.endswith((".json", ".dialogue.json")):
                try:
                    content: str | dict = json.loads(content_str)
                except json.JSONDecodeError:
                    # If a line in a JSON file isn't valid JSON, return an error message
                    # for that line. This can happen with empty lines or malformed entries.
                    content = f"JSONDecodeError: Could not parse line in {file_path}:{line_num}."
            else:
                content = content_str

            if file_path not in results:
                results[file_path] = []
            results[file_path].append((line_num, content))
        except (ValueError, IndexError):
            continue
    return results


def search_memory(terms: list[str]) -> dict | None:
    """
    Executes a `git grep` command to search for terms in durable memory,
    parses the output, and prints it as a YAML document.
    """
    command = ["git", "grep", "-i", "--line-number", "--all-match"]
    for term in terms:
        command.extend(["-e", term])
    command.extend(SEARCH_PATHS)

    try:
        # We run from within the .could-you directory
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=".could-you")

        if result.returncode == 1:
            # git grep returns 1 if no matches are found, which is not an error for us.
            LOGGER.info("No matches found.")
            return {}
        result.check_returncode()

        return _parse_git_grep_output(result.stdout)

    except FileNotFoundError:
        LOGGER.error("Error: `git` command not found. Is git installed and in your PATH?")
    except subprocess.CalledProcessError as e:
        LOGGER.error(f"Error executing git grep: {e.stderr}")
    return None
