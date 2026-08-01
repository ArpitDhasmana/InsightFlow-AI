"""Shared dimension groupings used across the agent pipeline."""

# Dimensions that represent a chronological series (rendered as a line chart,
# eligible for growth analysis).
TIME_DIMENSIONS = ("year", "fiscal_year", "quarter", "month", "week", "day")

# Coarse time dimensions where a short forward projection is meaningful.
FORECAST_DIMENSIONS = ("month", "quarter")
