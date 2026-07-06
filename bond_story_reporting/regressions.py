from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


def linear_story_trend(df: pd.DataFrame, story: str, metric: str = "can") -> dict:
    subset = df[df["story"] == story].sort_values("date")[["date", metric]].dropna()
    if len(subset) < 3:
        return {"story": story, "metric": metric, "status": "insufficient_data"}

    x = np.arange(len(subset)).reshape(-1, 1)
    y = subset[metric].to_numpy()
    model = LinearRegression().fit(x, y)
    next_value = float(model.predict(np.array([[len(subset)]]))[0])
    return {
        "story": story,
        "metric": metric,
        "status": "ok",
        "model": "linear",
        "slope": float(model.coef_[0]),
        "intercept": float(model.intercept_),
        "next_predicted_value": next_value,
    }


def polynomial_story_trend(
    df: pd.DataFrame,
    story: str,
    metric: str = "can",
    degree: int = 2,
) -> dict:
    subset = df[df["story"] == story].sort_values("date")[["date", metric]].dropna()
    if len(subset) < degree + 2:
        return {
            "story": story,
            "metric": metric,
            "status": "insufficient_data",
            "requested_degree": degree,
        }

    x = np.arange(len(subset), dtype=float)
    y = subset[metric].to_numpy(dtype=float)
    coeffs = np.polyfit(x, y, degree)
    poly = np.poly1d(coeffs)
    next_value = float(poly(len(subset)))

    return {
        "story": story,
        "metric": metric,
        "status": "ok",
        "model": "polynomial",
        "degree": degree,
        "coefficients": [float(c) for c in coeffs],
        "next_predicted_value": next_value,
    }
