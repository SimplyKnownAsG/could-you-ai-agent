import json
from pathlib import Path


def main():
    """Migrate old dialogue.json and backups to the new JSONL format."""
    try:
        workspace_config_dir = find_workspace_config_dir(Path.cwd())
    except FileNotFoundError:
        print("Error: No .could-you/ directory found. Run this script from within your project.")
        return

    print(f"Found workspace at: {workspace_config_dir.parent}")

    # 1. Migrate the live dialogue.json (with a safety check)
    old_live_dialogue = workspace_config_dir / "dialogue.json"
    new_live_dialogue = workspace_config_dir / "dialogue.jsonl"

    if new_live_dialogue.exists():
        print(f"Warning: {new_live_dialogue} already exists. Skipping migration of live dialogue to prevent data loss.")
    elif old_live_dialogue.exists():
        print(f"Migrating {old_live_dialogue} to {new_live_dialogue}...")
        convert_json_to_jsonl(old_live_dialogue, new_live_dialogue)
        print(f"-> Success. You can now safely delete {old_live_dialogue}")
    else:
        print("No live dialogue.json found to migrate.")

    print("-" * 20)

    # 2. Migrate backed-up dialogues
    old_backup_root = workspace_config_dir / "workspaces"
    new_archive_root = workspace_config_dir / "conversations"

    if old_backup_root.is_dir():
        print(f"Migrating backups from {old_backup_root} to {new_archive_root}...")
        new_archive_root.mkdir(exist_ok=True)
        migrated_count = 0

        for old_dialogue_path in sorted(old_backup_root.rglob("*.dialogue.json")):
            # Get the timestamp from the filename, per user's suggestion.
            # Example: "20260518T070841Z.dialogue.json" -> "20260518T070841Z"
            timestamp = old_dialogue_path.name.removesuffix(".dialogue.json")
            if not timestamp:
                print(f"  - Skipping {old_dialogue_path} (could not extract timestamp from filename).")
                continue

            new_filename = f"{timestamp}.jsonl"
            new_path = new_archive_root / new_filename

            if new_path.exists():
                print(f"  - Skipping {old_dialogue_path} (destination {new_path} already exists).")
                continue

            print(f"  - Migrating {old_dialogue_path.name} to {new_path.name}")
            convert_json_to_jsonl(old_dialogue_path, new_path)
            migrated_count += 1

        print(f"-> Migrated {migrated_count} backup files.")
        if migrated_count > 0:
            print(f"-> Success. You can now safely delete the {old_backup_root} directory.")
    else:
        print("No old backups found to migrate.")

    print("\nMigration complete.")


def convert_json_to_jsonl(source_path: Path, dest_path: Path):
    """Read a JSON file containing a list of objects and write a JSONL file."""
    try:
        with source_path.open() as infile, dest_path.open("w") as outfile:
            data = json.load(infile)
            if not isinstance(data, list):
                print(f"    - Warning: {source_path} is not a JSON list. Skipping.")
                return

            for item in data:
                json.dump(item, outfile)
                outfile.write("\n")
    except (OSError, json.JSONDecodeError) as e:
        print(f"    - Error converting {source_path}: {e}")


def find_workspace_config_dir(start_dir: Path) -> Path:
    """Walks up from start_dir looking for a .could-you directory."""
    current = start_dir.resolve()
    while True:
        potential_path = current / ".could-you"
        if potential_path.is_dir():
            return potential_path
        if current.parent == current:  # Root directory
            raise FileNotFoundError("No .could-you directory found.")
        current = current.parent


if __name__ == "__main__":
    main()
