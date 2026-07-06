from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE_PREFIX = "MBS_Analytics_Beta"

BASE_INCLUDE = [
    "bond_story_reporting",
    "config",
    "docs",
    "examples",
    "packaging",
    "sample_data",
    "scripts/build_beta_zip.py",
    "automation_saved_configs.json",
    "main.py",
    "README.md",
    "requirements.txt",
    "requirements-packaging.txt",
    "run_desktop_gui.bat",
    "run_nightly_config.bat",
]

SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "_audit_output",
    "_tmp_phase5_scan",
    "build",
    "dist",
    "dist_beta",
    "logs",
    "output",
    "runtime",
    "venv",
}

SKIP_FILE_GLOBS = {
    "*.bak",
    "*.log",
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.zip",
    "~$*",
}


def _app_version() -> str:
    init_path = PROJECT_ROOT / "bond_story_reporting" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _is_skipped(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT)
    if any(part in SKIP_DIR_NAMES for part in rel.parts[:-1]):
        return True
    if path.is_dir() and path.name in SKIP_DIR_NAMES:
        return True
    if any(path.match(pattern) for pattern in SKIP_FILE_GLOBS):
        return True
    return False


def _iter_included_files(include_tests: bool, include_demo_output: bool) -> list[Path]:
    entries = list(BASE_INCLUDE)
    if include_tests:
        entries.append("tests")
    if include_demo_output:
        entries.append("sample_output")

    files: list[Path] = []
    for entry in entries:
        source = PROJECT_ROOT / entry
        if not source.exists() or _is_skipped(source):
            continue
        if source.is_file():
            files.append(source)
            continue
        for item in source.rglob("*"):
            if item.is_file() and not _is_skipped(item):
                files.append(item)
    return sorted(set(files), key=lambda path: str(path.relative_to(PROJECT_ROOT)).lower())


def _copy_files(files: list[Path], package_root: Path) -> None:
    for source in files:
        target = package_root / source.relative_to(PROJECT_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _write_manifest(package_root: Path, files: list[Path], include_tests: bool, include_demo_output: bool) -> None:
    rel_files = [str(path.relative_to(PROJECT_ROOT)).replace("\\", "/") for path in files]
    manifest = [
        "MBS Analytics Beta Package Manifest",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"App version: {_app_version()}",
        f"Files included: {len(rel_files)}",
        f"Tests included: {include_tests}",
        f"Demo output included: {include_demo_output}",
        "",
        "Client launchers:",
        "- run_desktop_gui.bat",
        "- run_nightly_config.bat",
        "",
        "Runtime folders are created outside this package by default:",
        "- Documents/MBS Analytics/configs",
        "- Documents/MBS Analytics/logs",
        "- Documents/MBS Analytics/output",
        "",
        "Excluded from beta ZIP by design:",
        "- output/",
        "- logs/",
        "- runtime/",
        "- __pycache__/",
        "- _audit_output/",
        "- _tmp_phase5_scan/",
        "- build/dist folders",
        "",
        "Included files:",
        *rel_files,
        "",
    ]
    (package_root / "BETA_MANIFEST.txt").write_text("\n".join(manifest), encoding="utf-8")


def build_beta_zip(
    *,
    output_dir: Path,
    package_name: str,
    include_tests: bool,
    include_demo_output: bool,
    dry_run: bool,
) -> Path | None:
    files = _iter_included_files(include_tests=include_tests, include_demo_output=include_demo_output)
    if dry_run:
        print(f"Would include {len(files)} files.")
        for path in files[:120]:
            print(path.relative_to(PROJECT_ROOT))
        if len(files) > 120:
            print(f"... {len(files) - 120} more files")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    staging_parent = output_dir / "_staging"
    package_root = staging_parent / package_name
    if staging_parent.exists():
        shutil.rmtree(staging_parent)
    package_root.mkdir(parents=True)

    _copy_files(files, package_root)
    _write_manifest(
        package_root,
        files,
        include_tests=include_tests,
        include_demo_output=include_demo_output,
    )

    zip_path = output_dir / f"{package_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for item in package_root.rglob("*"):
            if item.is_file():
                zf.write(item, item.relative_to(staging_parent))

    shutil.rmtree(staging_parent)
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a clean beta delivery ZIP for MBS Analytics.")
    parser.add_argument("--output-dir", default="dist_beta", help="Folder where the beta ZIP is written.")
    parser.add_argument("--name", default=None, help="Optional package folder/zip name.")
    parser.add_argument("--include-tests", action="store_true", help="Include tests in the beta ZIP.")
    parser.add_argument(
        "--include-demo-output",
        action="store_true",
        help="Include sample_output/ if present. Old output/ folders are never included.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print included files without writing a ZIP.")
    args = parser.parse_args()

    package_name = args.name or f"{DEFAULT_PACKAGE_PREFIX}_{_app_version()}_{_timestamp()}"
    zip_path = build_beta_zip(
        output_dir=(PROJECT_ROOT / args.output_dir).resolve(),
        package_name=package_name,
        include_tests=args.include_tests,
        include_demo_output=args.include_demo_output,
        dry_run=args.dry_run,
    )
    if zip_path:
        print(f"Beta ZIP created: {zip_path}")


if __name__ == "__main__":
    main()
