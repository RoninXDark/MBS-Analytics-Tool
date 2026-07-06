from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


IDEA_SCAN_WORKFLOWS = {"idea_scan", "scan_ideas", "overnight_scan"}
LEGACY_WEEKLY_WORKFLOWS = {"weekly", "weekly_report", "run_weekly", "canned_report"}
FUTURE_WORKFLOWS = {"report_suite"}

WORKFLOW_ALIASES = {
    "ideas": "idea_scan",
    "idea_scan": "idea_scan",
    "scan_ideas": "idea_scan",
    "overnight_scan": "idea_scan",
    "overnight_ideas": "idea_scan",
    "buy_sell": "idea_scan",
    "buy_sell_scan": "idea_scan",
    "weekly": "weekly_report",
    "weekly_report": "weekly_report",
    "run_weekly": "weekly_report",
    "canned_report": "weekly_report",
    "payup_curves": "payup_curve_pack",
    "payup_curve_pack": "payup_curve_pack",
    "report_suite": "report_suite",
}


@dataclass(frozen=True)
class WorkflowResolution:
    """Normalized workflow choice for a saved configuration."""

    workflow: str
    requested_workflow: str | None
    inferred: bool = False


def normalize_workflow_name(value: Any) -> str:
    """Normalize workflow names from saved configs and CLI-style aliases."""

    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return WORKFLOW_ALIASES.get(raw, raw)


def detect_saved_workflow(config: Mapping[str, Any]) -> WorkflowResolution:
    """Return the workflow to run while preserving old saved-config behavior.

    Legacy weekly presets use ``auto_*`` fields and continue to route to the
    existing weekly runner. Idea-scan-shaped presets without an explicit
    ``workflow`` field are treated as ``idea_scan`` so older BUY/SELL configs
    keep working when the registry layer is introduced.
    """

    requested = _first_present(config, "workflow", "run_type", "type")
    if requested not in (None, ""):
        return WorkflowResolution(
            workflow=normalize_workflow_name(requested),
            requested_workflow=str(requested),
            inferred=False,
        )

    if _looks_like_legacy_weekly(config):
        return WorkflowResolution(workflow="weekly_report", requested_workflow=None, inferred=True)

    return WorkflowResolution(workflow="idea_scan", requested_workflow=None, inferred=True)


def implemented_workflows() -> list[str]:
    """Workflows currently executable through the registry."""

    return ["idea_scan", "payup_curve_pack", "weekly_report"]


def reserved_future_workflows() -> list[str]:
    """Workflow names reserved for later phases but not executable yet."""

    return sorted(FUTURE_WORKFLOWS)


def known_workflows() -> list[str]:
    return sorted(set(implemented_workflows()) | FUTURE_WORKFLOWS)


def _first_present(config: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = config.get(name)
        if value not in (None, ""):
            return value
    return None


def _looks_like_legacy_weekly(config: Mapping[str, Any]) -> bool:
    legacy_keys = {
        "auto_input",
        "auto_output",
        "auto_midweek",
        "auto_years",
        "auto_geos",
        "auto_coupons",
        "auto_buckets",
        "auto_issuer",
        "auto_rank_by",
        "auto_generate_excel_stats",
        "auto_generate_individual_charts",
        "auto_generate_versus_charts",
        "auto_best_n",
        "auto_worst_n",
    }
    return any(key in config for key in legacy_keys)
