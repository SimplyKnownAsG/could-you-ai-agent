# The function we will create in `could_you/memory/search.py`
from could_you.memory.search import _parse_git_grep_output

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
            (10, '{"role": "user", "content": "Can you search my memory?"}'),
            (11, '{"role": "assistant", "content": "Yes, I can search my memory."}'),
        ],
    }

    # The test `test_parse_git_grep_output_with_sample_data` will fail until this
    # function is implemented correctly.
    actual = _parse_git_grep_output(SAMPLE_GIT_GREP_OUTPUT)

    assert actual == expected
