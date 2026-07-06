from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    "date",
    "story",
    "story_bucket",
    "geo",
    "coupon",
    "year",
    "can",
    "payup",
    "spread",
    "issuer",
}


def _prepare_dataset(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["coupon"] = pd.to_numeric(df["coupon"], errors="coerce")
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    for col in ["can", "payup", "spread"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["story", "story_bucket", "geo", "issuer"]:
        df[col] = df[col].astype(str).str.strip()

    df = df.dropna(subset=["date", "coupon", "year", "can", "payup"])
    df = df.sort_values(["date", "story"]).reset_index(drop=True)
    return df


def load_dataset(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    return _prepare_dataset(df)


def load_dataset_from_filelike(file_obj: object, filename: str | None = None) -> pd.DataFrame:
    inferred_name = filename or str(getattr(file_obj, "name", ""))
    suffix = Path(inferred_name).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(file_obj)
    else:
        df = pd.read_csv(file_obj)
    return _prepare_dataset(df)


def apply_filters(
    df: pd.DataFrame,
    years: list[int] | None = None,
    geos: list[str] | None = None,
    coupons: list[float] | None = None,
    issuer: str | None = None,
    story_buckets: list[str] | None = None,
    stories: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    out = df.copy()
    if years:
        out = out[out["year"].isin(years)]
    if geos:
        out = out[out["geo"].isin(geos)]
    if coupons:
        out = out[out["coupon"].isin(coupons)]
    if issuer:
        out = out[out["issuer"].str.lower() == issuer.lower()]
    if story_buckets:
        out = out[out["story_bucket"].isin(story_buckets)]
    if stories:
        out = out[out["story"].isin(stories)]
    if date_from:
        out = out[out["date"] >= pd.to_datetime(date_from)]
    if date_to:
        out = out[out["date"] <= pd.to_datetime(date_to)]
    return out.reset_index(drop=True)
