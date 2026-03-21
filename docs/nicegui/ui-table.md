---
source: https://nicegui.io/documentation/table
fetched: 2026-03-13
library: nicegui
summary: ui.table (Quasar QTable) — columns, rows, pagination, selection, slots, cell templates
---

# ui.table — Quasar QTable Wrapper

Based on Quasar's [QTable](https://quasar.dev/vue-components/table) component.

## Basic Usage

```python
columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'required': True, 'align': 'left'},
    {'name': 'age', 'label': 'Age', 'field': 'age', 'sortable': True},
]
rows = [
    {'name': 'Alice', 'age': 18},
    {'name': 'Bob', 'age': 21},
]
table = ui.table(columns=columns, rows=rows, row_key='name')
```

## Key Properties

- `columns`: list of column defs (name, label, field, sortable, align, format, sort)
- `rows`: list of row dicts — update `table.rows = new_data` for incremental DOM update
- `row_key`: column used as unique row identifier
- `title`: optional table title
- `selection`: 'none' | 'single' | 'multiple'
- `pagination`: int (rows per page) or dict `{'rowsPerPage': N, 'sortBy': 'col', 'page': 1}`
- `column_defaults`: default properties for all columns
- `on_select`: callback for selection changes
- `on_pagination_change`: callback for pagination changes

## Updating Rows (No DOM Teardown)

Assigning `table.rows = new_list` triggers an incremental DOM update, preserving
pagination state, selection, and any Quasar notifications. This is the key advantage
over `@ui.refreshable` which destroys and recreates the entire container.

## Pagination

```python
ui.table(columns=columns, rows=rows, pagination=10)  # 10 rows per page
ui.table(columns=columns, rows=rows, pagination={'rowsPerPage': 4, 'sortBy': 'age', 'page': 2})
```

## Custom Cell Templates (Slots)

Since NiceGUI 3.5.0, use `table.cell()` context manager for clean slot definitions:

```python
table = ui.table(rows=[{'name': 'Alice', 'age': 18}])

# Custom cell for 'name' column
with table.add_slot('body-cell-name'):
    with table.cell('name'):
        ui.button().props(':label=props.value flat').on(
            'click',
            js_handler='() => emit(props.value)',
            handler=lambda e: ui.notify(f'Clicked {e.args}'),
        )

# Custom cell for 'age' column with conditional formatting
with table.add_slot('body-cell-age'):
    with table.cell('age'):
        ui.badge().props('''
            :label=props.value
            :color="props.value < 21 ? 'red' : 'green'"
        ''')
```

## Action Column with Buttons

```python
columns = [
    {'name': 'name', 'label': 'Name', 'field': 'name'},
    {'name': 'action', 'label': 'Action', 'align': 'center'},
]
table = ui.table(columns=columns, rows=rows)
with table.add_slot('body-cell-action'):
    with table.cell('action'):
        ui.button('Notify').props('flat').on(
            'click',
            js_handler='() => emit(props.row.name)',
            handler=lambda e: ui.notify(e.args),
        )
```

## Row Selection

```python
table = ui.table(
    columns=columns, rows=rows, row_key='name',
    selection='multiple',
    on_select=lambda e: ui.notify(f'selected: {e.selection}'),
)
# Access: table.selected → list of selected row dicts
```

## Data Retrieval Methods

- `await table.computed_rows()` — all computed rows
- `await table.computed_rows_number()` — row count
- `await table.filtered_sorted_rows()` — filtered/sorted rows

## Custom Sorting

```python
{'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True,
 ':sort': '(a, b, rowA, rowB) => b.length - a.length'}
```

## Custom Formatting

```python
{'name': 'age', 'label': 'Age', 'field': 'age',
 ':format': 'value => value + " years"'}
```

## Important Notes

- **Cells must not contain lists** — causes browser crashes. Convert to strings.
- `row_key` should be unique per row (use email or UUID).
- Updating `table.rows` does DOM diff, not full rebuild.
- Slots use Vue scoped slot syntax — `props.value`, `props.row`, `props.col`.
