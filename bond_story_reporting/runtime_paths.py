from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


APP_FOLDER_NAME = "MBS Analytics"
CONFIG_FILE_NAME = "automation_saved_configs.json"
SOURCE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    configs: Path
    logs: Path
    diagnostics: Path
    output: Path
    overnight_output: Path
    config_store: Path


def documents_dir() -> Path:
    """Return the user's Documents folder, with a safe home-folder fallback."""

    override = os.getenv("MBS_ANALYTICS_DOCUMENTS_DIR")
    if override:
        return Path(override).expanduser()

    documents = Path.home() / "Documents"
    return documents if documents.exists() else Path.home()


def local_appdata_dir() -> Path:
    """Return a user-writable local app-data folder for locked-down machines."""

    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata).expanduser()
    return Path.home() / "AppData" / "Local"


def temp_dir() -> Path:
    temp = os.getenv("TEMP") or os.getenv("TMP")
    if temp:
        return Path(temp).expanduser()
    return Path.home()


def runtime_root() -> Path:
    """Return the default writable runtime root for configs, logs, and outputs."""

    override = os.getenv("MBS_ANALYTICS_HOME")
    if override:
        return Path(override).expanduser()
    return documents_dir() / APP_FOLDER_NAME


def config_dir() -> Path:
    return runtime_root() / "configs"


def logs_dir() -> Path:
    return runtime_root() / "logs"


def diagnostics_dir() -> Path:
    return runtime_root() / "diagnostics"


def output_dir() -> Path:
    return runtime_root() / "output"


def overnight_output_dir() -> Path:
    return output_dir() / "overnight_ideas"


def default_config_store_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


def legacy_config_store_path() -> Path:
    return SOURCE_ROOT / CONFIG_FILE_NAME


def default_log_path(app_name: str = "bond_story_reporting") -> Path:
    return ensure_runtime_paths(migrate_legacy_config=False).logs / f"{app_name}.log"


def _runtime_paths_for_root(root: Path) -> RuntimePaths:
    configs = root / "configs"
    logs = root / "logs"
    diagnostics = root / "diagnostics"
    output = root / "output"
    overnight_output = output / "overnight_ideas"
    return RuntimePaths(
        root=root,
        configs=configs,
        logs=logs,
        diagnostics=diagnostics,
        output=output,
        overnight_output=overnight_output,
        config_store=configs / CONFIG_FILE_NAME,
    )


def _create_runtime_folders(paths: RuntimePaths) -> None:
    for folder in (
        paths.root,
        paths.configs,
        paths.logs,
        paths.diagnostics,
        paths.output,
        paths.overnight_output,
    ):
        folder.mkdir(parents=True, exist_ok=True)

    for folder in (paths.configs, paths.logs, paths.diagnostics, paths.output, paths.overnight_output):
        probe = folder / ".write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)


def ensure_runtime_paths(*, migrate_legacy_config: bool = True) -> RuntimePaths:
    """Create client-writable runtime folders and optionally migrate old configs."""

    candidates = [
        runtime_root(),
        local_appdata_dir() / APP_FOLDER_NAME,
        temp_dir() / APP_FOLDER_NAME,
        SOURCE_ROOT / "runtime",
    ]

    paths = None
    last_error: OSError | None = None
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.expanduser()
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        candidate_paths = _runtime_paths_for_root(candidate)
        try:
            _create_runtime_folders(candidate_paths)
            paths = candidate_paths
            break
        except OSError as exc:
            last_error = exc

    if paths is None:
        raise last_error or PermissionError("Could not create any MBS Analytics runtime folder.")

    legacy_store = legacy_config_store_path()
    if migrate_legacy_config and not paths.config_store.exists() and legacy_store.exists():
        shutil.copy2(legacy_store, paths.config_store)

    return paths


def resolve_default_config_store_path() -> Path:
    return ensure_runtime_paths().config_store


def resolve_default_overnight_output_dir() -> Path:
    return ensure_runtime_paths(migrate_legacy_config=False).overnight_output


def resolve_default_logs_dir() -> Path:
    return ensure_runtime_paths(migrate_legacy_config=False).logs


def resolve_default_diagnostics_dir() -> Path:
    return ensure_runtime_paths(migrate_legacy_config=False).diagnostics
