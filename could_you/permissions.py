import getpass
import os
import stat
from pathlib import Path
from typing import Any

try:
    import pwd
except ImportError:  # pragma: no cover - platform dependent
    pwd = None


def inspect_permission_boundary(w_config_dir: Path) -> dict[str, Any]:
    """Return an inspectable report about the current filesystem permission boundary.

    This does not create a sandbox. It reports what could-you can observe about the
    current process user and key workspace paths so a human can verify whether they
    are running could-you under the intended OS user / filesystem permissions.
    """
    w_config_dir = w_config_dir.resolve()
    workspace_root = w_config_dir.parent

    current_uid = os.geteuid() if hasattr(os, "geteuid") else None
    current_gid = os.getegid() if hasattr(os, "getegid") else None

    report: dict[str, Any] = {
        "currentUser": {
            "name": getpass.getuser(),
            "uid": current_uid,
            "gid": current_gid,
        },
        "workspaceRoot": str(workspace_root),
        "configDir": str(w_config_dir),
        "paths": {
            "workspaceRoot": _path_info(workspace_root),
            "configDir": _path_info(w_config_dir),
            "dialogueFile": _path_info(w_config_dir / "dialogue.json"),
            "dialogueParent": _path_info(w_config_dir),
        },
        "warnings": [],
        "notes": [
            "This report is observational; it does not create a sandbox or change permissions.",
            "MCP servers normally run as the same OS user as could-you unless their command wraps user switching.",
            "OS-user isolation protects files outside the agent user's permissions; subpath restrictions inside the workspace need tool-level controls too.",
        ],
    }

    warnings = report["warnings"]

    if current_uid == 0:
        warnings.append("could-you is running as root; this defeats the intended least-privilege boundary.")

    workspace_info = report["paths"]["workspaceRoot"]
    config_info = report["paths"]["configDir"]

    if not workspace_info["readable"]:
        warnings.append("Workspace root is not readable by the current user.")

    if not config_info["readable"]:
        warnings.append(".could-you is not readable by the current user.")

    if not config_info["writable"]:
        warnings.append(".could-you is not writable by the current user; dialogue and private memory updates may fail.")

    if config_info["worldReadable"]:
        warnings.append(".could-you appears world-readable; private workspace state may be exposed to other users.")

    if config_info["worldWritable"]:
        warnings.append(".could-you appears world-writable; private workspace state can be modified by other users.")

    if current_uid is not None and workspace_info["ownerUid"] == current_uid:
        report["notes"].append(
            "The current user owns the workspace root. That may be fine, but it is not evidence of a separate constrained agent user."
        )

    return report


def format_permission_report(report: dict[str, Any]) -> str:
    """Format a permission report for humans."""
    lines = [
        "Permission boundary report",
        "",
        f"Current user: {report['currentUser']['name']} "
        f"(uid={report['currentUser']['uid']}, gid={report['currentUser']['gid']})",
        f"Workspace root: {report['workspaceRoot']}",
        f"Config dir: {report['configDir']}",
        "",
        "Paths:",
    ]

    for label, info in report["paths"].items():
        lines.append(
            f"  {label}: exists={info['exists']} readable={info['readable']} "
            f"writable={info['writable']} executable={info['executable']} "
            f"owner={info['ownerName']}({info['ownerUid']}) mode={info['mode']}"
        )

    if report["warnings"]:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {warning}" for warning in report["warnings"])
    else:
        lines.extend(["", "Warnings: none"])

    lines.extend(["", "Notes:"])
    lines.extend(f"  - {note}" for note in report["notes"])

    return "\n".join(lines)


def _path_info(path: Path) -> dict[str, Any]:
    exists = path.exists()
    result: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "isDir": path.is_dir() if exists else False,
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
        "executable": os.access(path, os.X_OK),
        "ownerUid": None,
        "ownerName": None,
        "mode": None,
        "worldReadable": False,
        "worldWritable": False,
    }

    if not exists:
        return result

    st = path.stat()
    result["ownerUid"] = st.st_uid
    result["ownerName"] = _owner_name(st.st_uid)
    result["mode"] = stat.filemode(st.st_mode)
    result["worldReadable"] = bool(st.st_mode & stat.S_IROTH)
    result["worldWritable"] = bool(st.st_mode & stat.S_IWOTH)

    return result


def _owner_name(uid: int) -> str | None:
    if pwd is None:
        return None

    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return None
