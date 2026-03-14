# Using PromptGrimoire

Quick answers to common tasks and problems. Each entry shows you exactly what to click, with screenshots from the live application.

## Getting Started

### I want to log in for the first time

Navigate to the application URL. The production login page offers AAF SSO as the primary login method, with Google, GitHub, and magic link as alternatives. Use whichever method your institution supports.

For magic link login, enter your university email address and click **Send Magic Link**. Check your inbox for the login link.

See [Student Workflow - Step 1](student-workflow.md#step-1-logging-in) for a step-by-step walkthrough.

### How do I log in with my university (AAF) credentials?

Click **Login with AAF** on the login page. You will be redirected to the Australian Access Federation (AAF) identity hub, where you select your institution and authenticate with your usual university username and password. After a successful login you are returned to PromptGrimoire automatically.

**AAF is the recommended login method in production.** It uses your institution's own identity provider (SAML 2.0) so no separate PromptGrimoire password is required. Roles (e.g. `instructor`) are derived from the SAML attributes passed by your institution.

**Alternative methods** are available if AAF is not available to you:

- **Google or GitHub** -- OAuth login, available on the same login page.
- **Magic link** -- enter your Macquarie University email (`@mq.edu.au` or `@students.mq.edu.au`) and a one-time login link will be sent to your inbox. Magic links are restricted to MQ email domains.

If you see **"SSO not configured"**, contact your system administrator -- the AAF connection ID has not been set up in the deployment environment.

### I don't see any activities after logging in

**Diagnosis:** You are not enrolled in any units, or the instructor has not yet published any weeks with activities.

**Fix:** Check with your instructor that you are enrolled in the correct unit and semester. The instructor can verify your enrolment in Unit Settings.

See [Instructor Setup - Step 6](instructor-setup.md#step-6-enrolling-students) for how instructors add students to a unit.

## Workspaces

### I want to create a workspace for an activity

On the Navigator, find the activity your instructor assigned. Click **Start** to create your own workspace.

[![Navigator showing Start button for the activity](screenshots/using-promptgrimoire-01-thumb.png)](screenshots/using-promptgrimoire-01.png)

Your workspace inherits the tag configuration set by your instructor. You can start annotating immediately -- assuming the instructor has added content to the template. If the template has no documents, you will see a content form to paste or upload your own text first.

See [Student Workflow - Step 3](student-workflow.md#step-3-creating-a-workspace) for the full walkthrough.

### I configured tags but students can't see them

**Diagnosis:** You configured tags in your own workspace (a student instance), not the template. Tags set on instances only affect that workspace.

**Fix:** Go to **Unit Settings** and click the green **Create Template** or **Edit Template** button next to the activity. This opens the template workspace (purple chip). Configure tags there -- students will inherit them when they start the activity.

[![Unit Settings page showing Create Template button](screenshots/using-promptgrimoire-02-thumb.png)](screenshots/using-promptgrimoire-02.png)

See [Instructor Setup - Step 5](instructor-setup.md#step-5-configuring-tags-in-the-template) for a complete walkthrough.

### I clicked Start but wanted the template

The **Start** button on the Navigator creates your own student workspace (blue chip). To configure the activity for students, go to **Unit Settings** instead and click the green **Create Template** / **Edit Template** button.

Your student workspace is not wasted -- it is just your own working copy. It won't be visible to students unless you explicitly share it.

[![Start button creates a student workspace, not the template](screenshots/using-promptgrimoire-03-thumb.png)](screenshots/using-promptgrimoire-03.png)

## Tags

### I want to create a tag group for my activity

Open the template workspace from **Unit Settings**, then click the gear icon to open tag management.

[![Tag management dialog with Add Group button](screenshots/using-promptgrimoire-04-thumb.png)](screenshots/using-promptgrimoire-04.png)

Click **Add Group** to create a new tag group, then add tags within the group. Students will inherit this tag vocabulary when they start the activity.

See [Instructor Setup - Step 5](instructor-setup.md#step-5-configuring-tags-in-the-template) for a complete walkthrough.

### Tag import from another activity shows nothing

**Diagnosis:** The tag import dropdown lists any workspace you can read that contains tags. If no workspaces with tags appear, either no readable workspace has tags configured, or you configured tags in your own workspace instead of the template.

**Fix:** Open the source activity's template (Unit Settings -> Edit Template), configure tags there, then try the import again.

## Annotating

### I want to highlight text and apply a tag

Select text in your conversation by clicking and dragging. A tag menu appears -- click a tag to apply it.

[![Tag toolbar appearing after text selection](screenshots/using-promptgrimoire-05-thumb.png)](screenshots/using-promptgrimoire-05.png)

See [Student Workflow - Step 4](student-workflow.md#step-4-annotating---creating-a-highlight) for a detailed walkthrough.

### I want to add a comment to my highlight

Click on a highlight in the sidebar to expand it, then type your comment in the text input and click the post button.

[![Comment input on an annotation card](screenshots/using-promptgrimoire-06-thumb.png)](screenshots/using-promptgrimoire-06.png)

Comments let you record your analysis and reasoning. They appear below each highlight in the sidebar.

See [Student Workflow - Step 6](student-workflow.md#step-5-adding-a-comment) for a detailed walkthrough.

### Can I apply two different tags to the same text?

Yes. Overlapping highlights are fully supported. You can select a passage and apply multiple tags -- the highlighted regions can overlap partially or completely.

**How they display in the browser:** each tag has its own semi-transparent highlight colour (using the browser's CSS Custom Highlight API). Where two highlights overlap, both transparent colours layer on top of each other, producing a blended shade. An underline in the tag colour is also applied, so you can distinguish tags even where the background blending is subtle.

**How they display in PDF export:** the export pipeline uses an event-sweep algorithm to split the document into non-overlapping character regions, then renders each region with all active highlight colours blended. Regions covered by three or more overlapping highlights receive a dark neutral colour (#333333) to remain legible. Annotation markers (numbered superscripts) are placed at the end of each highlight.

**Practical advice:** overlapping highlights are useful when a single passage is relevant to more than one analytical category. If you find yourself applying every tag to every turn, consider whether your tag vocabulary needs refinement.

### Why can't I select or copy text from my workspace?

Your instructor has enabled **copy protection** on this activity. When active, the application intercepts copy, cut, right-click (context menu), drag, and print actions on the conversation text. A toast notification appears to explain why the action was blocked. An amber **Protected** chip is visible in the workspace header.

Copy protection also suppresses the browser print dialog (Ctrl+P / Cmd+P). If you need a printable copy of your work, use the **Export PDF** button instead -- the PDF is not affected by copy protection.

**Who bypasses copy protection:** instructors, coordinators, and system administrators are not subject to copy protection. The restriction applies only to students. If you are an instructor and see the Protected chip, check that your account has the correct role assigned in the authentication system.

**Turning copy protection on or off (instructors):** go to **Unit Settings** and open the unit settings dialog to toggle the default for the whole unit. Individual activities can override the unit default: in the activity row, use the per-activity copy protection selector -- **Inherit from unit**, **On**, or **Off**.

## Organising

### I want to view my highlights grouped by tag

Click the **Organise** tab to see your highlights arranged in columns by tag. You can drag highlights between columns to reclassify them.

[![Organise tab with highlights grouped by tag](screenshots/using-promptgrimoire-07-thumb.png)](screenshots/using-promptgrimoire-07.png)

See [Student Workflow - Step 7](student-workflow.md#step-6-organising-by-tag) for more details.

### What does the Locate button do on the Organise tab?

Each highlight card on the **Organise** tab and the reference panel on the **Respond** tab has a small map-pin icon button (tooltip: **Locate in document**).

Clicking **Locate** does two things:

1. **Switches you to the Annotate tab** -- the tab containing the source document
2. **Scrolls to the highlight** in the document and briefly flashes it gold so you can find it instantly

This is useful when you are on the Organise or Respond tab and want to re-read the surrounding context for a highlight without manually hunting for it in the document.

Locate is per-client only -- it navigates your own view and does not affect other users who are in the same workspace.

### I want to reorder or reclassify highlights on the Organise tab

On the **Organise** tab, highlight cards are draggable. Grab a card by clicking and holding, then drag it to its new position.

**Drag within a column** to reorder highlights under the same tag. The new order is saved and will persist across sessions and for collaborators in the same workspace.

**Drag between columns** to reassign a highlight to a different tag. The card moves to the target column and the highlight's tag is updated in the shared document.

All drag operations sync live to every connected client via the shared CRDT document -- collaborators see the updated order and tag assignments immediately without needing to reload.

If you need to scroll the Organise tab horizontally to reach a column that is off-screen, scroll the row of columns first, then drag. The columns scroll independently of the page.

## Responding

### I want to write a response using my highlights as reference

Click the **Respond** tab. Your highlights appear in the reference panel on the left; write your analysis in the markdown editor on the right.

[![Respond tab with editor and reference panel](screenshots/using-promptgrimoire-08-thumb.png)](screenshots/using-promptgrimoire-08.png)

See [Student Workflow - Step 8](student-workflow.md#step-7-writing-your-response) for a detailed walkthrough.

### Why does my response show a word count, and what do the colours mean?

When an instructor has configured word limits for an activity, a **word count badge** appears in the annotation page header while you write your response on the **Respond** tab. The badge shows your current count and, if a limit is set, the target.

**Badge colours:**

- **Grey** -- within acceptable range
- **Amber** -- approaching the limit (within 10%)
- **Red** -- over the word limit, or below the word minimum

Word counting uses multilingual tokenisation: Latin and Korean text use Unicode word-break rules (UAX #29), Chinese uses dictionary-based segmentation (jieba), and Japanese uses morphological analysis (MeCab). Zero-width characters and markdown link URLs are stripped before counting to prevent gaming the count.

**On PDF export:** if your response violates the word limit or falls below the minimum, a red violation badge is prepended to your exported PDF showing the current count and the configured threshold. If you are within limits, a neutral italic line shows the count instead. If no limits are configured, no badge appears.

Word limits are set by your instructor in the activity template. Contact your instructor if you believe the limit is incorrect or if you need an extension.

## Export

### I want to export my work as PDF

On the Annotate tab, click the **Export PDF** button. The export includes your conversation with highlights, comments, and written response.

[![Export PDF button on the annotation page](screenshots/using-promptgrimoire-09-thumb.png)](screenshots/using-promptgrimoire-09.png)

### What will my exported PDF be named?

The PDF filename is assembled automatically from your workspace metadata in this order:

``{UnitCode}_{LastName}_{FirstName}_{ActivityTitle}_{WorkspaceTitle}_{YYYYMMDD}.pdf``

**How each segment is derived:**

- **Unit code** -- the code set when the unit was created (e.g. ``LAWS1100``)
- **Last name / First name** -- taken from your display name; the system uses the last token as surname and the first token as given name
- **Activity title** -- the title of the activity your workspace belongs to
- **Workspace title** -- your workspace's title; omitted when it is the same as the activity title (the default for cloned workspaces)
- **Date** -- the server's local date at export time, formatted ``YYYYMMDD``

All segments are made filesystem-safe: special characters and spaces are replaced with underscores, and non-ASCII characters are transliterated. The total filename is capped at 100 characters; if it is too long, the workspace title is trimmed first, then the activity title, and finally the given name is reduced to an initial.

**Fallbacks when metadata is missing:** ``Unplaced`` (no unit), ``Loose_Work`` (no activity), ``Workspace`` (no workspace title), ``Unknown_Unknown`` (no display name).

To influence the filename, rename your workspace title before exporting -- the new title will appear as the workspace segment.

## Unit Settings

### I want to create a unit and activity

Navigate to **Units** and click **New Unit**. Fill in the unit code, name, and semester, then add weeks and activities.

[![Units page](screenshots/using-promptgrimoire-10-thumb.png)](screenshots/using-promptgrimoire-10.png)

See [Instructor Setup](instructor-setup.md#step-1-login-and-navigator) for the full step-by-step guide to creating a unit, adding weeks and activities, configuring tags, and enrolling students.

### How do I know if I'm in a template or instance?

Look at the coloured chip near the top of the annotation page:

- **Purple chip** saying "Template: [activity name]" -- you are editing the template. Changes here propagate to new student workspaces.

- **Blue chip** showing the activity name -- you are in a student workspace. Changes here are private to this workspace.

The chip is visible at the top of every annotation page. If you are unsure which workspace you are in, check the chip colour before making any tag or content changes.

### I want to rename a week, activity, or unit

**Renaming a week:** In Unit Settings, click the **Edit** button next to the week heading. A dialog opens where you can update the week number and title. Click **Save** to apply.

**Renaming an activity:** In Unit Settings, click the **Edit** button next to the activity. A dialog opens where you can update the activity title and description. Click **Save** to apply.

**Unit code and name:** The unit code and name are set when the unit is first created and cannot be changed through the UI. **Unit Settings** (the gear icon) only offers default policy toggles -- copy protection, sharing, and word count enforcement. If the code or name must change, an administrator can update it via the database.

**Edit buttons are only visible to instructors** with manage permission on the unit. Students do not see Edit buttons.

### What does 'Students with no work' mean?

On the Unit Settings page, an expandable panel labelled **Students with no work (N)** lists enrolled students who have not yet clicked **Start** on any activity in the unit. The number in parentheses is the count of those students.

[![Students with no work expansion on Unit Settings](screenshots/using-promptgrimoire-11-thumb.png)](screenshots/using-promptgrimoire-11.png)

**This does not mean anything is wrong.** It simply means those students have not started a workspace yet. Once you **publish** a week containing activities, students can see the activities on their Navigator and click **Start** to create their own workspace.

See [I want to make my activity visible to students](#i-want-to-make-my-activity-visible-to-students) for how to publish.

### I want to make my activity visible to students

Activities live inside **weeks**, and weeks have a **Published** / **Draft** status. Students can only see activities in published weeks -- draft weeks are invisible to them.

To publish: go to **Unit Settings**, find the week containing your activity, and click the **Publish** button next to the week heading. The status changes to **Published** and the activities in that week immediately appear on every enrolled student's Navigator with a **Start** button.

**Before publishing, check that:**

1. The template workspace has **content** added (otherwise students get an empty workspace)
2. **Tags** are configured on the template (students inherit the tag vocabulary)
3. Students are **enrolled** in the unit

See [I've enrolled students. What happens next?](#ive-enrolled-students-what-happens-next) for what students see after publishing.

## Enrolment

### I want to enrol students in my unit

On the unit detail page, click **Manage Enrollments**. This opens a separate enrolment page where you can enter student email addresses individually, or upload a bulk XLSX spreadsheet to add many students at once.

[![Manage Enrolments button in Unit Settings](screenshots/using-promptgrimoire-12-thumb.png)](screenshots/using-promptgrimoire-12.png)

See [Instructor Setup - Step 6](instructor-setup.md#step-6-enrolling-students) for a detailed walkthrough.

### I've enrolled students. What happens next?

Once students are enrolled, they log in and see the Navigator -- their home page. Any **published** activities in the unit appear automatically with a **Start** button.

[![Student Navigator showing enrolled unit and activities](screenshots/using-promptgrimoire-13-thumb.png)](screenshots/using-promptgrimoire-13.png)

When a student clicks **Start**, the application clones your template workspace -- they get their own copy with the content and tag configuration you set up. Students cannot see or modify the template itself.

**What to check before telling students to log in:**

1. The week containing the activity is **published** (unpublished weeks are invisible to students)
2. The template workspace has **content** added (otherwise students get an empty workspace)
3. **Tags** are configured on the template (students inherit the tag vocabulary)

### I want to enrol a whole cohort at once from Moodle

In **Manage Enrolments**, scroll past the single-email form to the **Bulk Enrol Students** section. Click the upload area and select your XLSX file.

**Where to get the file:** Export your class list from Moodle using **Gradebook -> Export -> Excel spreadsheet**. The parser expects these columns (case-insensitive): **First name**, **Last name**, **ID number**, and **Email address**. An optional **Groups** column is supported -- values like `[Tutorial 1], [Lab A]` are parsed automatically. Extra columns are ignored.

After upload, a notification reports how many students were enrolled and how many were skipped because they were already in the unit.

**Student ID conflicts:** If a student's Moodle ID number differs from the one already stored (e.g., a re-enrolment with a corrected ID), the upload stops and lists the conflicts. Tick **Override student ID conflicts** before uploading to force the new ID to win.

If the file fails validation, the upload reports every error before stopping -- for example, invalid email addresses or duplicate rows. Fix the XLSX and re-upload; the widget resets automatically.

### I enrolled a student but they don't have an account yet

You can enrol any email address even if the person has never logged in. When you click **Add** with an unknown email, the system creates a placeholder account in the local database and shows **"Enrollment added (new user created)"**.

The student does **not** receive any automatic notification. Tell them the application URL and ask them to log in. When they authenticate for the first time -- via AAF, Google, GitHub, or magic link -- their session is matched to the placeholder by email address and the enrolment activates immediately.

Until the student logs in, their name in the enrolment list is derived from the email prefix (e.g. `jsmith` from `jsmith@uni.edu`). It updates to their real display name on first login.

**Bulk upload:** The same behaviour applies to the XLSX bulk upload -- students who have never logged in receive placeholder accounts. There is no separate invitation step required.

## Housekeeping

### How do I clean up my test activities?

While learning the system you may have created test activities or clicked **Start** on your own activities. Now you want to tidy up, but the delete button says workspaces exist.

**Why this happens:** Clicking **Start** on an activity creates a student workspace (a clone of the template). Even though you are the instructor, the system treats this as a student workspace -- and activities cannot be deleted while student workspaces exist.

**How to clean up:**

1. **Delete student workspaces first.** On the Navigator, find the workspace you created by clicking Start. Click the trash icon on the workspace card to delete it.
2. **Then delete the activity, week, or unit directly.** Once no student workspaces remain, you can delete at any level -- deleting a week cascades to its activities, and deleting a unit cascades to its weeks and activities.

The rule is: **student workspaces block deletion** at every level (activity, week, and unit). You must clear them first. But the structural entities themselves cascade automatically -- you do not need to delete activities before weeks, or weeks before units.

**Admin shortcut:** Admin users have a **force-delete** option that purges student workspaces and cascades automatically -- no need to manually delete workspaces first.

## Navigation

### I want to find my workspace

The Navigator is your home page. It shows all your workspaces organised by unit and activity.

[![Navigator showing workspaces](screenshots/using-promptgrimoire-14-thumb.png)](screenshots/using-promptgrimoire-14.png)

Click on a workspace to open it. Your most recent workspaces appear at the top.

### I want to search across my workspaces

Use the search bar at the top of the Navigator to find workspaces by content, tag, or comment text.

[![Search bar on the Navigator](screenshots/using-promptgrimoire-15-thumb.png)](screenshots/using-promptgrimoire-15.png)

Full-text search looks across your highlights, tags, comments, and response text.

## Sharing & Collaboration

### I want to share my workspace with someone

Open the workspace you want to share. Click the **Share** button in the toolbar to open the sharing dialog.

[![Share button in the workspace toolbar](screenshots/using-promptgrimoire-16-thumb.png)](screenshots/using-promptgrimoire-16.png)

Enter the email address of the person you want to share with. They will see your workspace on their Navigator.

**Note:** The Share button is only visible to workspace owners and privileged users (instructors and admins). Sharing by email only works for users who already have an account -- the system cannot send invitations to addresses with no existing account.

### How do other students view my workspace?

There are two ways a classmate can see your workspace:

**1. Share with class toggle.** If your instructor has enabled peer sharing for the activity, a **Share with class** toggle appears in your workspace toolbar. Switching it on lets every enrolled student in the unit view your workspace. They get **peer** access -- read-only. They can see your highlights, comments, tags, and response, but cannot change anything.

**2. Share by email.** The workspace owner (and instructors) can click **Share** in the toolbar to open the sharing dialog. Enter a classmate's email address and choose **Viewer** or **Editor** permission. Viewer is read-only; Editor allows them to add highlights and comments alongside you.

**What peer access means:** A student with peer access sees your workspace on their Navigator. They can read everything in it, but the workspace remains yours -- they cannot delete highlights, change tags, or modify your response.

**If the toggle is missing:** The instructor has not enabled peer sharing for the activity. Contact your instructor to ask them to turn on sharing in the activity settings.

### Can multiple people work in the same workspace at the same time?

Yes. PromptGrimoire uses **CRDT** (Conflict-free Replicated Data Type) synchronisation, so multiple people can be in the same workspace simultaneously without overwriting each other's work. Changes merge automatically -- no locking, no "someone else is editing" warnings.

**What syncs in real time:**

- Highlights (creating, deleting, moving between tags)
- Comments on highlights
- Tags and tag groups
- General notes
- Response draft (the markdown editor on the Respond tab)

**Who is connected?** The toolbar shows a small badge -- for example **2 users** -- counting everyone currently viewing the workspace. Each connected user is assigned a distinct colour for their cursor and presence indicator.

**Common use case:** An instructor opens a student's workspace to leave comments at the same time the student is working. Both see each other's changes appear within seconds.

**Note:** Real-time sync requires an active connection. If you lose connectivity, your changes are queued locally and sync when the connection is restored. Work is never lost.

## Content Input

### I want to upload a document instead of pasting

When you first open a workspace that has no content yet, you see the content form. Below the paste editor there is an **Upload** button for importing files directly.

Supported formats: PDF (.pdf), Word (.docx), Markdown (.md), HTML, and plain text. The document is converted to annotatable text automatically.

The upload option appears on the initial content form when a workspace has no documents. It also reappears as **Add Document** when multi-document mode is enabled for the activity.

### What AI platforms can I paste conversations from?

PromptGrimoire automatically detects the source platform when you paste a conversation and strips the native UI chrome (buttons, labels, avatars). Speaker turns are re-labelled with uniform **User:** and **Assistant:** markers so you can annotate consistently regardless of where the conversation came from.

**Supported platforms (auto-detected):**

- **ChatGPT** (OpenAI) -- copy the conversation page in your browser
- **Claude** (Anthropic) -- copy the conversation page in your browser
- **Gemini** (Google) -- copy the conversation page in your browser
- **AI Studio** (Google) -- copy the conversation page in your browser
- **OpenRouter** -- copy the conversation page in your browser
- **ChatCraft** -- copy the conversation page in your browser
- **ScienceOS** -- copy the conversation page in your browser
- **Wikimedia** -- copy the conversation page in your browser
- **Plain text** -- any platform not listed above; paste as-is

**How to paste:** Open your workspace, click into the content area, and paste (Ctrl+V / Cmd+V). The pipeline detects the format from the clipboard structure -- HTML with recognisable platform markers is preprocessed automatically; plain text is wrapped in paragraphs.

**File upload alternative:** PDF (.pdf) and Word (.docx) files can be uploaded directly using the **Upload** button on the initial content form. The document is converted to annotatable HTML automatically. See [I want to upload a document instead of pasting](#i-want-to-upload-a-document-instead-of-pasting) for details.

**If your platform is not listed:** paste as plain text. The content will be imported without automatic speaker labelling. You can still annotate all the text; you will just need to identify turns manually.
