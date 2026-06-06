# Sample Input Format

MBS Analytics Tool supports Bloomberg-style wide files and residual history files.

## Price / OAS Wide Format

A typical file has one security identifier column and many date columns.

```csv
Bond,2026-01-05,2026-01-12,2026-01-19
2023 FNCL 5.0 NY,100-163,100-181,100-195
2023 FNCL 5.0 FL,100-097,100-112,100-128
2024 FNCL 4.5 TX,99-28+,100-002,100-041
```

The loader scans the first rows to find date-like headers, then uses the strongest text column as the bond/security identifier.

## Residuals Format

Residual workflows need bond names, dates, and a residual metric column.

```csv
Bond,Date,Residual
2023 FNCL 5.0 NY,2026-01-05,0-04+
2023 FNCL 5.0 NY,2026-01-12,0-03
2023 FNCL 5.0 FL,2026-01-12,-0-02
```

The residual report ranks the richest and cheapest securities and writes an Excel workbook plus charts.

## Privacy

Do not commit real Bloomberg exports, client workbooks, generated charts, or reports. Keep only small anonymized examples in `examples/`.