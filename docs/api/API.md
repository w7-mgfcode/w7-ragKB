# API Reference

## Authentication

All endpoints require a valid JWT Bearer token unless otherwise noted.

```
Authorization: Bearer <access_token>
```

---

## Documents

### GET /api/documents/tree

Returns the hierarchical document tree structure.

**Auth Required:** Yes (Bearer token)

**Response (200):**
```json
[
  {
    "type": "directory",
    "name": "security",
    "path": "security",
    "children": [
      {
        "type": "document",
        "name": "auth-guide.md",
        "path": "security/auth-guide.md",
        "metadata": { "size": 2048, "modified": "2026-02-20T10:00:00Z", "word_count": 350 }
      }
    ]
  }
]
```

### GET /api/documents/stats

Returns aggregate document statistics.

**Response (200):**
```json
{ "total_directories": 2, "total_documents": 10, "total_subdirectories": 3, "total_words": 5430 }
```

### GET /api/documents/{path}

Fetch a single document by path.

**Response (200):**
```json
{ "path": "security/auth-guide.md", "content": "# Auth Guide\n...", "metadata": { "size": 2048, "modified": "...", "word_count": 350 } }
```

### POST /api/documents

Create a new document.

**Request:**
```json
{ "path": "guides/new-guide.md", "content": "# New Guide\n\nContent here." }
```

**Response (201):** Created document object

### PUT /api/documents/{path}

Update an existing document.

**Request:**
```json
{ "content": "# Updated content" }
```

**Response (200):** Updated document object

### DELETE /api/documents/{path}

Delete a document.

**Response (200):**
```json
{ "message": "Deleted", "path": "guides/old-guide.md" }
```

### POST /api/documents/search

Search documents by content or filename.

**Request:**
```json
{ "query": "authentication" }
```

**Response (200):**
```json
[{ "path": "security/auth-guide.md", "name": "auth-guide.md", "matches": [{ "type": "content", "snippet": "...authentication flow...", "position": 42 }], "metadata": { "size": 2048, "modified": "...", "word_count": 350 } }]
```

### POST /api/documents/directories

Create a new directory.

**Request:** `{ "path": "new-category" }`

**Response (201):** `{}`

### DELETE /api/documents/directories/{path}

Delete an empty directory.

**Response (200):** `{}`

**Error (400):** Directory not empty

### GET /api/documents/directories

List all directories.

**Response (200):** `["security", "operations"]`

### POST /api/documents/bulk-delete

Delete multiple documents.

**Request:** `{ "paths": ["doc1.md", "doc2.md"] }`

**Response (200):** `{ "successful": ["doc1.md"], "failed": [] }`

### POST /api/documents/bulk-move

Move multiple documents to a target directory.

**Request:** `{ "paths": ["doc1.md"], "target_directory": "archive" }`

**Response (200):** `{ "successful": ["doc1.md"], "failed": [] }`

### GET /api/documents/categories

Get category tree with document counts.

**Response (200):** CategoryNode array

### GET /api/documents/category-stats

Get per-category statistics with chunk level distribution.

**Response (200):** CategoryStats array

### POST /api/documents/route-query

Route a search query to relevant document categories using LLM.

**Request:** `{ "query": "how do I authenticate?" }`

**Response (200):** `{ "categories": ["security"], "reasoning": "...", "confidence": 0.95 }`

### GET /api/documents/sync-status

Get sync status for all tracked documents (filesystem vs database).

**Response (200):**
```json
[
  {
    "file_path": "security/auth-guide.md",
    "sync_status": "in_sync",
    "filesystem_mtime": "2026-02-20T10:00:00Z",
    "database_mtime": "2026-02-20T10:00:00Z",
    "chunk_count": 5,
    "error_message": null,
    "source": "filesystem",
    "last_checked": "2026-02-28T12:00:00Z"
  }
]
```

**Sync Status Values:** `in_sync`, `out_of_sync`, `processing`, `error`, `orphaned_chunks`, `pending_indexing`

### GET /api/documents/sync-status/{path}

Get sync status for a single document.

**Response (200):** Single DocumentSyncInfo object (same shape as array items above)

### POST /api/documents/reindex/{path}

Manually trigger re-indexing for a single document. Rate limited.

**Response (200):** Updated DocumentSyncInfo object

### POST /api/documents/reindex-directory/{path}

Trigger re-indexing for all documents in a directory. Rate limited.

**Response (200):** Array of DocumentSyncInfo objects

### POST /api/documents/reindex-all

Trigger re-indexing for all documents. Rate limited. Concurrency controlled by `SYNC_REINDEX_CONCURRENCY` (default 3).

**Response (200):** Array of DocumentSyncInfo objects

### POST /api/documents/resolve-conflict/{path}

Resolve a conflict between filesystem and database versions of a document. Rate limited.

**Request:**
```json
{ "strategy": "keep_filesystem" }
```

**Strategies:** `keep_filesystem`, `keep_database`, `manual_merge`

For `manual_merge`, include the merged content:
```json
{ "strategy": "manual_merge", "merged_content": "# Merged content\n..." }
```

**Response (200):** Resolved Document object

### WebSocket /api/documents/ws

Real-time document update notifications via WebSocket.

**Auth:** Pass JWT token as query parameter: `/api/documents/ws?token=<access_token>`

**Server-sent message types:**
- `sync_status_update` — A document's sync status changed
- `document_created` — A new document was created
- `document_updated` — A document was modified
- `document_deleted` — A document was deleted
- `reindex_complete` — A re-indexing operation finished

**Message format:**
```json
{ "type": "sync_status_update", "data": { "file_path": "docs/guide.md", "sync_status": "in_sync" }, "timestamp": "2026-02-28T12:00:00Z" }
```

### Error Responses (Documents)

- **400** — Validation error (invalid filename, empty content)
- **401** — Unauthorized (missing/expired JWT)
- **404** — Document or directory not found
- **409** — Conflict (filename already exists)
- **429** — Rate limited (100 req/60s per user for mutations)
- **500** — Internal server error
