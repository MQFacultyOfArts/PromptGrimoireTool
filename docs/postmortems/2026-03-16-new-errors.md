# New Errors Observed 2026-03-16 ~15:00 AEDT

Reported during/after class following the #360/#361 deploy.

## 1. Export Failure

- Workspace: `d692d101-d4d4-4a04-9e11-ccf1d79d04db`
- Discord alert: `[ERROR] latex_subprocess_output`
- PID: 1168211 (post-deploy process)
- Likely pre-existing (known LaTeX compilation issues with certain content)
- Need to check: `sudo journalctl -u promptgrimoire --no-pager -S "15:00" -U "15:10" | grep d692d101`

## 2. Tag Organise Regression

- Colour/name changes not propagating to the primary client
- Debounce-related
- Was previously fixed — regression suggests the #361 changes may have affected the save/propagation path
- Key files: `tag_management_save.py`, `tag_management.py`
- Need to check: did the `_unique_default_name` refactor or `DuplicateNameError` catch change the control flow for normal (non-duplicate) saves?

## 3. Select ValueError

- `ui.select` rebuilt with empty options but stale UUID value
- "Lots of slot deletion errors"
- This matches the `list.index(x): x not in list` and `The parent element this slot belongs to has been deleted` errors from the morning incident
- May be a separate pre-existing race in the annotation page rebuild cycle
- Need to check: `sudo journalctl -u promptgrimoire -f -p err` for ValueError traces
