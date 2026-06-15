# ADR-001: JSONL Storage for Dialogue History

## Status

Proposed

## Context

The current dialogue storage mechanism uses a single JSON file (`.could-you/dialogue.json`) for the entire conversation history of a workspace. The `Dialogue` class loads this entire file into memory at the start of a session and writes the entire, potentially modified, list of messages back to the file at the end.

This approach has several drawbacks:
1.  **Inefficiency:** For long-running conversations, the file can become very large, leading to high memory usage and slow serialization/deserialization times.
2.  **Data Loss Risk:** If the agent process is interrupted or crashes, any new messages from that session that have not yet been written to the file are lost.
3.  **Search Complexity:** Searching requires either loading the entire file or using text-based tools that are not optimized for structured JSON.
4.  **Compaction Brittleness:** The memory compaction process is tied to this single-file model, operating on the entire in-memory list of messages.

A more robust and scalable solution is required, especially considering the need for long-term, searchable memory that respects LLM context window limitations.

## Decision

We will transition to a hybrid JSON Lines (JSONL) storage model that separates the active "working buffer" from the long-term, archived history.

1.  **Active Dialogue Buffer:**
    *   A single, well-known file named `.could-you/dialogue.jsonl` will serve as the active conversation buffer.
    *   New messages will be appended as a single line (a JSON object) to this file, which is an efficient, atomic operation.
    *   On startup, the agent will load all messages from the `.could-you/dialogue.jsonl` file. This mirrors the current system's behavior of loading the entire active dialogue history into memory. The existing memory pressure warnings (based on token count after loading) will continue to function as they do today.

2.  **Archived Conversations:**
    *   A new directory, `.could-you/conversations/`, will be created to store historical dialogue.
    *   The memory compaction process (`compact-history` script) will be updated. After summarizing the dialogue and updating `MEMORY.md`, it will **archive** the current `.could-you/dialogue.jsonl` by renaming it to `.could-you/conversations/<timestamp>.jsonl` (e.g., `20240730T102900Z.jsonl`).
    *   A new, empty `.could-you/dialogue.jsonl` will be created to start the next conversation cycle.

3.  **Search:**
    *   Memory search functionality (`--search-memory`) will be configured to run `git grep` across the archived files in `.could-you/conversations/*.jsonl`, as well as other memory files (`MEMORY.md`, `TODO.md`, etc.). It will *not* search the active `dialogue.jsonl`.

## Consequences

### Positive

*   **Robustness:** Appending lines is atomic and significantly reduces the risk of data loss on crash. Only the last in-flight message could be lost.
*   **Performance:** I/O is much faster. We only append new messages, rather than rewriting the entire history file on every run.
*   **Scalability:** The system can handle a virtually infinite history, as only the active buffer and the long-term compacted memories are loaded into context.
*   **Clarity:** The separation of concerns is clear:
    *   `MEMORY.md`: High-signal, compacted long-term memory.
    *   `dialogue.jsonl`: High-detail, short-term working memory.
    *   `conversations/*.jsonl`: Searchable, long-term archival memory.
*   **Simplicity:** The backup mechanism becomes simpler. It only needs to commit new `.jsonl` files in the `conversations` directory, rather than copying files.

### Negative

*   **Migration Required:** A one-time migration script will be needed to convert existing `dialogue.json` files and backups into the new JSONL archive format.
*   **Slightly More Complex Logic:** The `Dialogue` class will need to handle both appending to the active file and loading history by reading the file in reverse.

This decision aligns with the core tenets of making the system more robust, auditable, and explicit in its operation.
