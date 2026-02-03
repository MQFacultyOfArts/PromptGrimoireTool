# Issue #42: Student Progress Report - Grid View

## Summary
Create a grid/table view showing student completion status across all lesson sessions. This is **URGENT** - needed immediately so Jen can follow up with Week 2 participants.

## Grid Structure
- **Rows**: Students (by display name)
- **Columns**: Session IDs (Day 1, Day 2, Day 3, etc.)
- **Cells**: Color-coded status
  - Green (`positive`) = Completed
  - Yellow (`warning`) = In Progress (active)
  - Grey = Not Started

## Implementation Plan

### Step 1: Create the progress page
Create `/app/pages/admin_progress.py` following the existing admin page patterns:

```python
@ui.page("/admin/progress")
@require_role("admin")
async def admin_progress():
    # ... page content
```

**Key logic:**
1. Fetch all users (for admin to see all participants)
2. For each user, fetch their runs with `RunService.get_user_runs()`
3. Build a matrix: `{(user, student): {session_id: status}}`
4. Render as a grid with color-coded cells

### Step 2: Build the data aggregation
Query all runs and aggregate by:
- User email (or display name)
- Student display name
- Session ID (day1, day2, day3, etc.)

Determine status per cell:
- If any run has `status="completed"` → Completed (green)
- If any run has `status="active"` → In Progress (yellow)
- If no run exists → Not Started (grey)

### Step 3: Create the UI grid
Use the same pattern as [admin.py:96-144](app/pages/admin.py#L96-L144):
- `ui.column()` container with `ui.row()` for each row
- Header row with session names
- Data rows with student names and colored status cells
- Use `bg-eucalyptus-green`, `bg-sunshine-yellow`, `bg-gray-200` for status colors

### Step 4: Register the page
Update [/app/pages/__init__.py](app/pages/__init__.py) to import the new module.

### Step 5: Add navigation link
Add a "View Progress" button on [admin.py](app/pages/admin.py) linking to `/admin/progress`.

## Files to Modify
1. **Create**: `/app/pages/admin_progress.py` - New progress grid page
2. **Edit**: `/app/pages/__init__.py` - Register the new page
3. **Edit**: `/app/pages/admin.py` - Add navigation link to progress page

## Key Code References
- [Run model](app/models/run.py) - status field: `active`, `paused`, `completed`, `abandoned`
- [RunService.get_user_runs()](app/services/run_service.py#L70-L95) - Fetches all runs with related data
- [Theme colors](app/ui/theme.py#L22-L33) - `eucalyptus-green` (success), `sunshine-yellow` (in-progress)
- [Admin page pattern](app/pages/admin.py#L16-L18) - `@ui.page` + `@require_role` decorators

## Verification
1. Run the server and navigate to `/admin/progress`
2. Verify grid shows all students across rows
3. Verify columns show all unique session IDs (day1, day2, etc.)
4. Verify color coding matches run status
5. Test with no runs, partial runs, and completed runs
