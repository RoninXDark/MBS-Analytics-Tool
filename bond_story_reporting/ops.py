from __future__ import annotations

import importlib
import json
import platform
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .config import get_default_config
from .runtime_paths import resolve_default_diagnostics_dir
from .utils import ensure_dir, now_iso


def _module_version(module_name: str) -> str:
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        return "missing"
    return str(getattr(mod, "__version__", "installed"))


def run_doctor(output_dir: str | Path | None = None) -> dict:
    output_dir = output_dir or resolve_default_diagnostics_dir()
    output_root = ensure_dir(output_dir)
    python_info = {
        "version": sys.version.split(" ")[0],
        "executable": sys.executable,
        "platform": platform.platform(),
    }

    dependencies = {
        "pandas": _module_version("pandas"),
        "numpy": _module_version("numpy"),
        "matplotlib": _module_version("matplotlib"),
        "openpyxl": _module_version("openpyxl"),
        "yaml": _module_version("yaml"),
        "sklearn": _module_version("sklearn"),
        "ttkbootstrap": _module_version("ttkbootstrap"),
    }

    cfg = get_default_config()
    output_probe = output_root / "write_probe.tmp"
    writeable = True
    write_error = None
    try:
        output_probe.write_text("ok", encoding="utf-8")
        output_probe.unlink(missing_ok=True)
    except Exception as exc:
        writeable = False
        write_error = str(exc)

    health = {
        "generated_at": now_iso(),
        "python": python_info,
        "dependencies": dependencies,
        "config_keys": sorted(cfg.keys()),
        "filesystem": {
            "diagnostics_dir": str(Path(output_root).resolve()),
            "writeable": writeable,
            "write_error": write_error,
        },
    }

    output_path = output_root / "doctor_report.json"
    output_path.write_text(json.dumps(health, indent=2, ensure_ascii=False), encoding="utf-8")
    return health


def bundle_output_artifacts(
    source_dir: str | Path,
    bundle_path: str | Path | None = None,
) -> Path:
    source = Path(source_dir)
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Source output directory not found: {source}")

    if bundle_path is None:
        bundle_path = source.parent / f"{source.name}_bundle.zip"
    bundle = Path(bundle_path)
    ensure_dir(bundle.parent)

    with ZipFile(bundle, mode="w", compression=ZIP_DEFLATED) as zf:
        for file_path in source.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(source))

    return bundle
