/**
 * API client for RAG Document Browser
 * 
 * Provides functions for document CRUD operations, search, bulk operations,
 * and hierarchical RAG features (categories, query routing).
 * 
 * All requests include JWT authentication via authFetch.
 * Implements exponential backoff retry logic for resilience.
 */

import { authFetch, getAccessToken } from './auth-client';
import type {
  TreeNode,
  Document,
  DocumentStats,
  SearchRequest,
  SearchResult,
  CreateDocumentRequest,
  UpdateDocumentRequest,
  DeleteResponse,
  CreateDirectoryRequest,
  DirectoryResponse,
  BulkDeleteRequest,
  BulkMoveRequest,
  BulkOperationResult,
  CategoryNode,
  QueryRoutingRequest,
  QueryRoutingResponse,
  DocumentSyncInfo,
  ConflictResolution,
} from '@/types/documents';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const DOCUMENTS_BASE = `${API_BASE}/api/documents`;

// ============================================================================
// Retry Logic with Exponential Backoff
// ============================================================================

interface RetryConfig {
  maxRetries: number;
  baseDelay: number;
  maxDelay: number;
}

const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelay: 1000,
  maxDelay: 4000,
};

/**
 * Execute a function with exponential backoff retry logic
 * Delays: 1s, 2s, 4s (max 3 retries)
 */
async function withRetry<T>(
  fn: () => Promise<T>,
  config: RetryConfig = DEFAULT_RETRY_CONFIG
): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;

      // Don't retry on client errors (4xx except 429) or auth errors
      if (error instanceof Response) {
        const status = error.status;
        if (status >= 400 && status < 500 && status !== 429) {
          throw error;
        }
      }

      // If this was the last attempt, throw the error
      if (attempt === config.maxRetries) {
        throw lastError;
      }

      // Calculate delay with exponential backoff: 1s, 2s, 4s
      const delay = Math.min(
        config.baseDelay * Math.pow(2, attempt),
        config.maxDelay
      );

      // Wait before retrying
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}

// ============================================================================
// Document Tree & Stats
// ============================================================================

/**
 * Get the complete document tree structure
 */
export async function getDocumentTree(): Promise<TreeNode[]> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/tree`);
    if (!res.ok) throw new Error(`Failed to fetch document tree: ${res.status}`);
    return res.json();
  });
}

/**
 * Get aggregate statistics about the document collection
 */
export async function getDocumentStats(): Promise<DocumentStats> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/stats`);
    if (!res.ok) throw new Error(`Failed to fetch document stats: ${res.status}`);
    return res.json();
  });
}

// ============================================================================
// Document CRUD Operations
// ============================================================================

/**
 * Get a document by path
 * @param path - Document path relative to rag-documents root
 */
export async function getDocument(path: string): Promise<Document> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/${encodeURIComponent(path)}`);
    if (!res.ok) throw new Error(`Failed to fetch document: ${res.status}`);
    return res.json();
  });
}

/** Alias used by DocumentPreview */
export const fetchDocument = getDocument;

/**
 * Create a new document
 * @param path - Document path (must end with .md)
 * @param content - Initial markdown content
 */
export async function createDocument(path: string, content: string): Promise<Document> {
  return withRetry(async () => {
    const payload: CreateDocumentRequest = { path, content };
    const res = await authFetch(`${DOCUMENTS_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to create document: ${error}`);
    }
    return res.json();
  });
}

/**
 * Update an existing document
 * @param path - Document path relative to rag-documents root
 * @param content - Updated markdown content
 */
export async function updateDocument(path: string, content: string): Promise<Document> {
  return withRetry(async () => {
    const payload: UpdateDocumentRequest = { content };
    const res = await authFetch(`${DOCUMENTS_BASE}/${encodeURIComponent(path)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to update document: ${error}`);
    }
    return res.json();
  });
}

/**
 * Delete a document
 * @param path - Document path relative to rag-documents root
 */
export async function deleteDocument(path: string): Promise<DeleteResponse> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/${encodeURIComponent(path)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to delete document: ${error}`);
    }
    return res.json();
  });
}

// ============================================================================
// Search
// ============================================================================

/**
 * Search documents by name or content
 * @param query - Search query string
 * @param searchContent - If true, search file content; if false, only filenames
 */
export async function searchDocuments(query: string, searchContent: boolean = true): Promise<SearchResult[]> {
  return withRetry(async () => {
    const payload: SearchRequest = { query, search_content: searchContent };
    const res = await authFetch(`${DOCUMENTS_BASE}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to search documents: ${error}`);
    }
    return res.json();
  });
}

// ============================================================================
// Directory Management
// ============================================================================

/**
 * Create a new directory
 * @param path - Directory path relative to rag-documents root
 */
export async function createDirectory(path: string): Promise<DirectoryResponse> {
  return withRetry(async () => {
    const payload: CreateDirectoryRequest = { path };
    const res = await authFetch(`${DOCUMENTS_BASE}/directories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to create directory: ${error}`);
    }
    return res.json();
  });
}

/**
 * Delete an empty directory
 * @param path - Directory path relative to rag-documents root
 */
export async function deleteDirectory(path: string): Promise<DirectoryResponse> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/directories/${encodeURIComponent(path)}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to delete directory: ${error}`);
    }
    return res.json();
  });
}

// ============================================================================
// Bulk Operations
// ============================================================================

/**
 * Delete multiple documents in a single operation
 * @param paths - Array of document paths to delete
 */
export async function bulkDeleteDocuments(paths: string[]): Promise<BulkOperationResult> {
  return withRetry(async () => {
    const payload: BulkDeleteRequest = { paths };
    const res = await authFetch(`${DOCUMENTS_BASE}/bulk-delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to bulk delete documents: ${error}`);
    }
    return res.json();
  });
}

/**
 * Move multiple documents to a target directory
 * @param paths - Array of document paths to move
 * @param targetDir - Target directory path
 */
export async function bulkMoveDocuments(paths: string[], targetDir: string): Promise<BulkOperationResult> {
  return withRetry(async () => {
    const payload: BulkMoveRequest = { paths, target_directory: targetDir };
    const res = await authFetch(`${DOCUMENTS_BASE}/bulk-move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to bulk move documents: ${error}`);
    }
    return res.json();
  });
}

// ============================================================================
// Hierarchical RAG Features
// ============================================================================

/**
 * Get the category tree with document counts and metadata
 */
export async function getCategories(): Promise<CategoryNode[]> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/categories`);
    if (!res.ok) throw new Error(`Failed to fetch categories: ${res.status}`);
    return res.json();
  });
}

/**
 * Use LLM to route a query to relevant categories
 * @param query - User's search query
 * @param maxCategories - Maximum number of categories to select (default: 3)
 */
export async function routeQuery(query: string, maxCategories?: number): Promise<QueryRoutingResponse> {
  return withRetry(async () => {
    const payload: QueryRoutingRequest = { query, max_categories: maxCategories };
    const res = await authFetch(`${DOCUMENTS_BASE}/route-query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to route query: ${error}`);
    }
    return res.json();
  });
}

// ============================================================================
// Sync Status & Re-indexing
// ============================================================================

/**
 * Get sync statuses for all documents
 */
export async function getAllSyncStatuses(): Promise<DocumentSyncInfo[]> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/sync-status`);
    if (!res.ok) throw new Error(`Failed to fetch sync statuses: ${res.status}`);
    return res.json();
  });
}

/**
 * Get sync status for a specific document
 * @param path - Document path relative to rag-documents root
 */
export async function getSyncStatus(path: string): Promise<DocumentSyncInfo> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/sync-status/${encodeURIComponent(path)}`);
    if (!res.ok) throw new Error(`Failed to fetch sync status: ${res.status}`);
    return res.json();
  });
}

/**
 * Re-index a single document (re-chunk and re-embed)
 * @param path - Document path relative to rag-documents root
 */
export async function reindexDocument(path: string): Promise<DocumentSyncInfo> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/reindex/${encodeURIComponent(path)}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to re-index document: ${error}`);
    }
    return res.json();
  });
}

/**
 * Re-index all documents in a directory (recursive)
 * @param path - Directory path relative to rag-documents root
 */
export async function reindexDirectory(path: string): Promise<DocumentSyncInfo[]> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/reindex-directory/${encodeURIComponent(path)}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to re-index directory: ${error}`);
    }
    return res.json();
  });
}

/**
 * Re-index all documents in the entire collection
 */
export async function reindexAll(): Promise<DocumentSyncInfo[]> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/reindex-all`, {
      method: 'POST',
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to re-index all documents: ${error}`);
    }
    return res.json();
  });
}

/**
 * Resolve a document conflict
 * @param path - Document path relative to rag-documents root
 * @param resolution - Conflict resolution strategy
 */
export async function resolveConflict(path: string, resolution: ConflictResolution): Promise<Document> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/resolve-conflict/${encodeURIComponent(path)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(resolution),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to resolve conflict: ${error}`);
    }
    return res.json();
  });
}

// ============================================================================
// Metadata Management
// ============================================================================

/**
 * Update document metadata without triggering re-indexing
 * @param path - Document path relative to rag-documents root
 * @param metadata - Metadata fields to update (title, author, tags)
 */
export async function updateDocumentMetadata(
  path: string,
  metadata: { title?: string; author?: string; tags?: string[] }
): Promise<{ message: string; path: string; updated_fields: string[] }> {
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/${encodeURIComponent(path)}/metadata`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(metadata),
    });
    if (!res.ok) {
      const error = await res.text();
      throw new Error(`Failed to update metadata: ${error}`);
    }
    return res.json();
  });
}

// ============================================================================
// Error Handling Utilities
// ============================================================================

/**
 * Extract error message from error object
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  return 'An unknown error occurred';
}

/**
 * Check if error is a network error
 */
export function isNetworkError(error: unknown): boolean {
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return true;
  }
  if (error instanceof Error && error.message.includes('network')) {
    return true;
  }
  return false;
}

/**
 * Check if error is a timeout error
 */
export function isTimeoutError(error: unknown): boolean {
  if (error instanceof Error && error.message.includes('timeout')) {
    return true;
  }
  return false;
}

/**
 * Get stats for a specific category (stub — not yet in backend)
 */
export async function getCategoryStats(categoryPath?: string): Promise<any> {
  const query = categoryPath ? `?category=${encodeURIComponent(categoryPath)}` : '';
  return withRetry(async () => {
    const res = await authFetch(`${DOCUMENTS_BASE}/category-stats${query}`);
    if (!res.ok) throw new Error(`Failed to fetch category stats: ${res.status}`);
    return res.json();
  });
}
