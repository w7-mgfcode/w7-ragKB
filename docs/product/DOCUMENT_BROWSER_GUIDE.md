# RAG Document Browser — User Guide

## Overview

The Document Browser provides a web-based interface for browsing, creating, editing, and managing documents in the RAG knowledge base. Documents stored here are automatically indexed for AI-powered retrieval and question answering.

## Accessing the Document Browser

Navigate to `/documents` in the web application. You must be logged in.

## Browsing Documents

### Tree View

The left panel displays documents in a hierarchical tree structure organized by directories (categories). Click a directory to expand/collapse its contents.

### Statistics Panel

The top of the page shows aggregate statistics:
- **Spaces/Categories** — Number of directories
- **Pages/Documents** — Total document count
- **Words** — Total word count across all documents

### Searching

Use the search bar at the top of the tree to filter documents by name or content. Results appear as you type (300ms debounce). Press Escape or click the X button to clear the search.

**Keyboard shortcut:** Press `Ctrl+F` to focus the search bar.

## Managing Documents

### Creating a Document

1. Click the **New Document** button
2. Enter a filename (must end in `.md`)
3. Select a target directory (optional)
4. Write or paste markdown content
5. Click **Create**

### Viewing a Document

Click any document in the tree to view its rendered markdown content in the right panel. The viewer shows:
- Document title and path
- Word count, file size, and last modified date
- Rendered markdown with syntax highlighting

### Editing a Document

1. Click a document to view it
2. Click the **Edit** button
3. Modify the content in the editor
4. Click **Save** (or press `Ctrl+S`)
5. Click **Cancel** to discard changes

**Auto-recovery:** If saving fails, your content is automatically saved to browser storage and offered for recovery on your next visit.

### Deleting a Document

1. Click a document to view it
2. Click the **Delete** button
3. Confirm deletion in the dialog

### Bulk Operations

1. Expand directories to see documents
2. Use the checkboxes to select multiple documents
3. The bulk actions toolbar appears with:
   - **Delete** — Delete all selected documents (with confirmation)
   - **Move** — Move selected documents to a different directory
   - **Re-index** — Trigger re-indexing for selected documents
   - **Clear** — Deselect all documents

## Sync Status

Each document shows a sync status badge indicating whether the filesystem and database are in agreement.

### Status Indicators

| Badge | Status | Meaning |
|-------|--------|---------|
| Green checkmark | **In Sync** | Filesystem and database match |
| Yellow warning | **Out of Sync** | Filesystem is newer than database |
| Blue spinner | **Processing** | Currently being indexed |
| Red circle | **Error** | Indexing failed (hover for details) |
| Orange warning | **Orphaned** | Database chunks exist but file is missing |
| Gray clock | **Pending** | File exists but has not been indexed yet |

Sync statuses update in real-time via WebSocket. A 60-second polling fallback ensures updates even if the WebSocket connection drops.

## Re-indexing

Re-indexing forces the system to re-read and re-embed a document's content.

### Re-index a Single Document

1. Click a document to view it
2. Click the **Re-index** button in the viewer toolbar
3. Confirm in the dialog
4. The status badge will show "Processing" until complete

### Re-index a Directory

1. Select documents via checkboxes, or use the bulk toolbar
2. Click **Re-index** in the bulk actions toolbar
3. All selected documents will be queued for re-indexing

### Re-index All Documents

Available through the Re-index dialog by selecting the "all" scope. Concurrency is limited (default: 3 simultaneous) to avoid overloading the system.

## Conflict Resolution

When a document's filesystem and database versions diverge, a conflict may be detected.

### Resolving Conflicts

1. The document viewer will show an "Out of Sync" badge
2. Open the conflict resolution dialog
3. Compare the filesystem and database versions side by side
4. Choose a resolution strategy:
   - **Keep Filesystem** — Overwrite database with filesystem version
   - **Keep Database** — Overwrite filesystem with database version
   - **Manual Merge** — Edit the content manually and save

## Keyboard Navigation

The document tree supports full keyboard navigation:

| Key | Action |
|-----|--------|
| `Arrow Down` | Move to next visible node |
| `Arrow Up` | Move to previous visible node |
| `Arrow Right` | Expand directory / move to first child |
| `Arrow Left` | Collapse directory / move to parent |
| `Enter` | Select document / toggle directory |
| `Home` | Jump to first node |
| `End` | Jump to last node |
| `Tab` / `Shift+Tab` | Move focus in/out of tree |
| `Ctrl+F` | Focus search bar |
| `Ctrl+S` | Save (in editor) |
| `Escape` | Clear search / cancel edit |

## Accessibility

The Document Browser is designed for WCAG 2.1 AA compliance:
- Full keyboard navigation (no mouse required)
- ARIA tree pattern for screen readers
- Screen reader announcements for expand/collapse actions
- Skip link to jump directly to the document tree
- Visible focus indicators for keyboard users
- Sync status badges use `role="status"` with descriptive `aria-label` for screen readers
