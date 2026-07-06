from __future__ import annotations

from pathlib import Path
from typing import Any

from ..presets import DEFAULT_CONFIG_STORE_PATH, read_saved_config, run_saved_configuration
from .canned_reports import run_saved_payup_curve_pack
from .idea_scan import IdeaScanRunDefinition, run_idea_scan_definition
from .run_definitions import (
    WorkflowResolution,
    detect_saved_workflow,
    implemented_workflows,
    known_workflows,
    reserved_future_workflows,
)


class UnsupportedWorkflowError(ValueError):
    """Raised when a saved config asks for a workflow this build cannot run."""


def available_workflows(*, include_future: bool = True) -> list[str]:
    """Return workflow names known to the saved-config registry."""

    return known_workflows() if include_future else implemented_workflows()


def resolve_saved_workflow(config: dict[str, Any]) -> WorkflowResolution:
    """Normalize and infer the workflow for a saved config."""

    return detect_saved_workflow(config)


def run_saved_idea_scan_workflow(
    config_name: str,
    config: dict[str, Any],
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the existing BUY/SELL idea scan through the registry layer."""

    definition = IdeaScanRunDefinition.from_mapping(config, base_dir=base_dir)
    result = run_idea_scan_definition(definition)
    return {
        "config_name": config_name,
        "workflow": "idea_scan",
        "input_path": str(definition.input_path),
        "output_path": str(result.output_dir),
        "run_metadata_path": str(result.run_metadata_path),
        "metadata": result.run_metadata,
    }


def run_saved_workflow(
    config_name: str,
    config_store_path: str | Path = DEFAULT_CONFIG_STORE_PATH,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run a saved configuration using the workflow registry.

    This is intentionally a thin dispatch layer. Existing workflow executors
    stay unchanged so the working beta behavior remains stable.
    """

    config = read_saved_config(config_name=config_name, config_store_path=config_store_path)
    resolution = resolve_saved_workflow(config)

    if resolution.workflow == "idea_scan":
        return run_saved_idea_scan_workflow(config_name=config_name, config=config, base_dir=base_dir)

    if resolution.workflow == "weekly_report":
        result = run_saved_configuration(
            config_name=config_name,
            config_store_path=config_store_path,
            base_dir=base_dir,
        )
        return {"workflow": "weekly_report", **result}

    if resolution.workflow == "payup_curve_pack":
        return run_saved_payup_curve_pack(config_name=config_name, config=config, base_dir=base_dir)

    raise _unsupported_workflow_error(config_name=config_name, resolution=resolution)


def _unsupported_workflow_error(config_name: str, resolution: WorkflowResolution) -> UnsupportedWorkflowError:
    if resolution.workflow in reserved_future_workflows():
        return UnsupportedWorkflowError(
            f"Saved config '{config_name}' uses workflow '{resolution.workflow}', "
            "but that workflow is reserved for a future phase and is not implemented in this beta yet. "
            f"Currently supported workflows: {', '.join(implemented_workflows())}."
        )

    known = ", ".join(available_workflows(include_future=True))
    supported = ", ".join(implemented_workflows())
    return UnsupportedWorkflowError(
        f"Saved config '{config_name}' uses unsupported workflow '{resolution.workflow}'. "
        f"Known workflow names: {known}. Currently implemented workflows: {supported}."
    )
