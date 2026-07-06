"""Legacy MBS foundation code integrated from MBS_project.zip."""

from .backend import (
    filter_by_period,
    generate_charts,
    generate_curve_analysis,
    generate_residual_line_chart,
    generate_spread_chart,
    load_residuals_data,
    load_timeseries_data,
    process_residuals_scatter,
)
from .utils import format_32nds, parse_mbs_price

__all__ = [
    "filter_by_period",
    "format_32nds",
    "generate_charts",
    "generate_curve_analysis",
    "generate_residual_line_chart",
    "generate_spread_chart",
    "load_residuals_data",
    "load_timeseries_data",
    "parse_mbs_price",
    "process_residuals_scatter",
]
