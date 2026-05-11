/**
 * TypeScript type definitions for the RAG Document Browser
 * 
 * These types match the backend API response models exactly.
 * They support hierarchical document organization, search, bulk operations,
 * and category-based query routing for the RAG system.
 */

// ============================================================================
// Tree Structure Types
// ============================================================================

/**
 * Metadata associated with a document file
 */
export interface DocumentMetadata {
  /** File size in bytes */
  size: number;
  /** Last modified timestamp (ISO 8601 format) */
  modified: string;
  /** Total word count in the document */
  word_count: number;
}

/**
 * Directory node in the document tree
 */
export interface DirectoryTreeNode {
  type: 'directory';
  /** Directory name (not full path) */
  name: string;
  /** Full path relative to rag-documents root */
  path: string;
  /** Child nodes (directories and documents) */
  children: TreeNode[];
  /** Client-side state: whether directory is expanded */
  expanded?: boolean;
  /** Client-side state: whether directory is selected */
  selected?: boolean;
}

/**
 * Document node in the document tree
 */
export interface DocumentTreeNode {
  type: 'document';
  /** Document filename (not full path) */
  name: string;
  /** Full path relative to rag-documents root */
  path: string;
  /** Document metadata (size, modified, word count) */
  metadata: DocumentMetadata;
  /** Client-side state: whether document is selected */
  selected?: boolean;
}

/**
 * Union type representing either a directory or document node
 */
export type TreeNode = DirectoryTreeNode | DocumentTreeNode;

// ============================================================================
// Document Content Types
// ============================================================================

/**
 * Complete document with content and metadata
 */
export interface Document {
  /** Full path relative to rag-documents root */
  path: string;
  /** Markdown content of the document */
  content: string;
  /** Document metadata */
  metadata: DocumentMetadata;
}

// ============================================================================
// Statistics Types
// ============================================================================

/**
 * Aggregate statistics about the document collection
 */
export interface DocumentStats {
  /** Total number of top-level directories (categories/spaces) */
  total_directories: number;
  /** Total number of documents (pages) */
  total_documents: number;
  /** Total number of subdirectories (sections) */
  total_subdirectories: number;
  /** Total word count across all documents */
  total_words: number;
}

// ============================================================================
// Search Types
// ============================================================================

/**
 * Request payload for document search
 */
export interface SearchRequest {
  /** Search query string */
  query: string;
  /** If true, search file content; if false, only search filenames */
  search_content: boolean;
}

/**
 * A single match within a search result
 */
export interface SearchMatch {
  /** Type of match: filename or content */
  type: 'filename' | 'content';
  /** Text snippet showing the match with surrounding context */
  snippet: string;
  /** Character offset of the match in the document */
  position: number;
}

/**
 * Search result for a single document
 */
export interface SearchResult {
  /** Full path relative to rag-documents root */
  path: string;
  /** Document filename */
  name: string;
  /** Array of matches found in this document */
  matches: SearchMatch[];
  /** Document metadata */
  metadata: DocumentMetadata;
}

// ============================================================================
// Bulk Operation Types
// ============================================================================

/**
 * Request payload for bulk delete operation
 */
export interface BulkDeleteRequest {
  /** Array of document paths to delete */
  paths: string[];
}

/**
 * Request payload for bulk move operation
 */
export interface BulkMoveRequest {
  /** Array of document paths to move */
  paths: string[];
  /** Target directory path */
  target_directory: string;
}

/**
 * Result of a bulk operation (delete or move)
 */
export interface BulkOperationResult {
  /** Array of paths that were successfully processed */
  successful: string[];
  /** Array of failed operations with error messages */
  failed: Array<{ path: string; error: string }>;
}

// ============================================================================
// Directory Management Types
// ============================================================================

/**
 * Request payload for creating a new directory
 */
export interface CreateDirectoryRequest {
  /** Directory path relative to rag-documents root */
  path: string;
}

/**
 * Response from directory operations (create/delete)
 */
export interface DirectoryResponse {
  /** Success or error message */
  message: string;
  /** Directory path that was affected */
  path: string;
}

// ============================================================================
// Document CRUD Types
// ============================================================================

/**
 * Request payload for creating a new document
 */
export interface CreateDocumentRequest {
  /** Document path relative to rag-documents root (must end with .md) */
  path: string;
  /** Initial markdown content (can be empty string) */
  content: string;
}

/**
 * Request payload for updating a document
 */
export interface UpdateDocumentRequest {
  /** Updated markdown content */
  content: string;
  /** Optional expected mtime for conflict detection (ISO 8601) */
  expected_mtime?: string;
}

/**
 * Request payload for updating document metadata without re-indexing
 */
export interface UpdateMetadataRequest {
  title?: string;
  author?: string;
  tags?: string[];
}

/**
 * Response from document deletion
 */
export interface DeleteResponse {
  /** Success message */
  message: string;
  /** Path of the deleted document */
  path: string;
}

// ============================================================================
// Hierarchical RAG Types
// ============================================================================

/**
 * Category node in the hierarchical category tree
 */
export interface CategoryNode {
  /** Category name (directory name) */
  name: string;
  /** Full category path (e.g., "infrastructure/networking") */
  path: string;
  /** Number of documents in this category */
  document_count: number;
  /** Total number of chunks (all levels) in this category */
  total_chunks: number;
  /** Subcategories (nested directories) */
  subcategories: CategoryNode[];
}

/**
 * Request payload for LLM-based query routing
 */
export interface QueryRoutingRequest {
  /** User's search query */
  query: string;
  /** Maximum number of categories to select (default: 3) */
  max_categories?: number;
}

/**
 * Response from LLM-based query routing
 */
export interface QueryRoutingResponse {
  /** Original query */
  query: string;
  /** Array of selected category paths */
  selected_categories: string[];
  /** LLM's explanation for category selection */
  reasoning: string;
  /** Confidence score (0.0 to 1.0) */
  confidence: number;
}

/**
 * Statistics for a specific category
 */
export interface CategoryStats {
  /** Category path (e.g., "infrastructure/networking") */
  category_path: string;
  /** Number of documents in this category */
  document_count: number;
  /** Total number of chunks in this category */
  total_chunks: number;
  /** Distribution of chunks by level */
  chunk_level_distribution: {
    /** Number of document-level chunks */
    document: number;
    /** Number of section-level chunks */
    section: number;
    /** Number of leaf-level chunks */
    leaf: number;
  };
  /** Average chunk size in tokens */
  avg_chunk_size: number;
  /** Total word count across all documents in this category */
  total_words: number;
  /** Last update timestamp (ISO 8601 format) */
  last_updated: string;
}

// ============================================================================
// Sync Status Types
// ============================================================================

/**
 * Document synchronization status between filesystem and database
 */
export type SyncStatus =
  | 'in_sync'
  | 'out_of_sync'
  | 'processing'
  | 'error'
  | 'orphaned_chunks'
  | 'pending_indexing';

/**
 * Sync information for a document
 */
export interface DocumentSyncInfo {
  file_path: string;
  sync_status: SyncStatus;
  filesystem_mtime: string | null;
  database_mtime: string | null;
  chunk_count: number;
  error_message: string | null;
  source: 'filesystem' | 'browser';
  last_checked: string | null;
}

/**
 * Information about a document conflict between filesystem and database
 */
export interface ConflictInfo {
  file_path: string;
  filesystem_content: string;
  database_content: string;
  filesystem_mtime: string;
  database_mtime: string;
  conflict_type: 'content_mismatch' | 'missing_file' | 'missing_chunks';
}

/**
 * Resolution strategy for a document conflict
 */
export interface ConflictResolution {
  strategy: 'keep_filesystem' | 'keep_database' | 'manual_merge';
  merged_content?: string;
}

/**
 * Result of a re-indexing operation
 */
export interface ReindexResult {
  path: string;
  status: 'success' | 'failed' | 'skipped';
  sync_info?: DocumentSyncInfo;
  error_message?: string;
}

// ============================================================================
// Theme Types
// ============================================================================

/**
 * Theme mode for the document browser
 */
export type Theme = 'light' | 'dark';

// ============================================================================
// Editor State Types
// ============================================================================

/**
 * State for the document editor component
 */
export interface EditorState {
  /** Path of the document being edited */
  path: string;
  /** Current content in the editor */
  content: string;
  /** Original content before editing */
  originalContent: string;
  /** Whether the content has unsaved changes */
  isDirty: boolean;
  /** Whether a save operation is in progress */
  isSaving: boolean;
  /** Timestamp of last successful save (ISO 8601 format) */
  lastSaved: string | null;
  /** Error message if save failed */
  error: string | null;
}
