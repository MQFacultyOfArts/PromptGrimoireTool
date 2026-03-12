---
source: https://openpyxl.readthedocs.io/en/stable/optimized.html
fetched: 2026-03-12
library: openpyxl
summary: Read-only mode for memory-efficient XLSX parsing, load_workbook API, iter_rows usage
---

# openpyxl Read-Only Mode & Core API

## load_workbook

Opens an Excel file and returns a Workbook object.

```python
from openpyxl import load_workbook

wb = load_workbook(filename='example.xlsx', read_only=True)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filename` | str or file-like | required | Path to file or binary file-like object |
| `read_only` | bool | `False` | Optimised for reading, content cannot be edited |
| `keep_vba` | bool | `False` | Preserve VBA content |
| `data_only` | bool | `False` | Return last calculated value instead of formula |
| `keep_links` | bool | `True` | Preserve links to external workbooks |
| `rich_text` | bool | `False` | Preserve rich text formatting |

### Read-Only Mode

When `read_only=True`:
- Near-constant memory consumption for large files
- All worksheets are `ReadOnlyWorksheet` (lazy loading)
- Cells are `ReadOnlyCell` instances (not standard cells)
- **Must explicitly close** with `wb.close()` to free resources
- Workbook is read-only (no edits)

```python
from openpyxl import load_workbook

wb = load_workbook(filename='large_file.xlsx', read_only=True)
ws = wb['big_data']

for row in ws.rows:
    for cell in row:
        print(cell.value)

wb.close()
```

## iter_rows

Produces cells from the worksheet, by row. Specify iteration range using indices.

```python
# Cell objects
for row in ws.iter_rows(min_row=1, max_col=3, max_row=2):
    for cell in row:
        print(cell)
# <Cell Sheet1.A1>, <Cell Sheet1.B1>, ...

# Values only (tuples of values)
for row in ws.iter_rows(min_row=1, max_col=3, max_row=2, values_only=True):
    print(row)
# (None, None, None)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_row` | int | None | Smallest row index (1-based) |
| `max_row` | int | None | Largest row index (1-based) |
| `min_col` | int | None | Smallest column index (1-based) |
| `max_col` | int | None | Largest column index (1-based) |
| `values_only` | bool | `False` | Return only cell values instead of Cell objects |

## iter_cols

Same as `iter_rows` but iterates column by column.

```python
for col in ws.iter_cols(min_row=1, max_col=3, max_row=2):
    for cell in col:
        print(cell)
```

**Note:** `iter_cols` is not available in read-only mode.

## Worksheet Properties

- `ws.max_row` — Largest row index with data (may overcount with padding)
- `ws.max_column` — Largest column index with data
- `ws.sheetnames` — List of sheet names (on workbook, not worksheet)

## Cell Access

```python
# Single cell
cell = ws['A1']
cell = ws.cell(row=1, column=1)

# Range
cells = ws['A1:D5']

# Entire row/column
row = ws[4]
col = ws['A']
```
