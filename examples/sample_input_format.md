# Sample Input Format

The tool supports both a canonical long format and Bloomberg-style wide exports.

## Canonical Long Format

Use this format when each row already represents one observation for one bond/story/date.

Required or commonly used columns:

| Column | Example | Notes |
| --- | --- | --- |
| `date` | `2026-04-19` | Observation date. |
| `story` | `2023 FNCL 5.0 NY` | Human-readable bond/story label. |
| `story_bucket` | `FNCL` | Program or story family. |
| `geo` | `NY` | Geography/state bucket. |
| `coupon` | `5.0` | Coupon bucket. |
| `year` | `2023` | Vintage/origination year. |
| `can` | `1.42` | Z-score/CAN-style metric when available. |
| `payup` | `0.35` | Payup metric used in ranking and charting. |
| `spread` | `45.0` | Spread or relative-value metric. |
| `issuer` | `FNCL` | Issuer/program label. |

Minimal CSV example:

```csv
date,story,story_bucket,geo,coupon,year,can,payup,spread,issuer
2026-04-19,2023 FNCL 5.0 NY,FNCL,NY,5.0,2023,1.42,0.35,45.0,FNCL
2026-04-26,2023 FNCL 5.0 NY,FNCL,NY,5.0,2023,1.31,0.31,43.0,FNCL
```

## Bloomberg-Style Wide Format

Wide files are supported when dates appear as column headers and rows represent bonds/stories. The normalizer detects date-like headers, melts the data into long format, and then parses story dimensions such as program, geography, coupon, and vintage where possible.

Example shape:

```csv
Bond,2026-04-19,2026-04-26,2026-05-03
2023 FNCL 5.0 NY,100-163,100-181,100-195
2023 FNCL 5.0 FL,100-097,100-112,100-128
```

## MBS Price Notation

The foundation workflows support MBS 32nds-style prices such as:

- `100-16`
- `100-163`
- `99-287`

These are parsed into decimal prices for charting and spread calculations, then formatted back into market-readable notation where needed.

## Privacy Note

Do not commit client workbooks, Bloomberg exports, generated Excel reports, or production saved configs. Keep only small anonymized samples in `sample_data/` or documentation examples in `examples/`.