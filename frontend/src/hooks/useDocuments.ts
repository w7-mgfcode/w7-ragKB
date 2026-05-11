/**
 * React Query hooks for document operations.
 * 
 * Provides data fetching, caching, and mutation hooks with optimistic updates
 * and automatic cache invalidation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/use-toast';
import * as documentsApi from '@/lib/documents-api';
import type {
  TreeNode,
  DocumentStats,
  Document,
  CreateDocumentRequest,
  UpdateDocumentRequest,
  SearchRequest,
  SearchResult,
  CreateDirectoryRequest,
  BulkDeleteRequest,
  BulkMoveRequest,
  DocumentSyncInfo,
  ConflictResolution,
} from '@/types/documents';

// Query keys
const QUERY_KEYS = {
  tree: ['documents', 'tree'] as const,
  stats: ['documents', 'stats'] as const,
  document: (path: string) => ['documents', 'document', path] as const,
  search: (query: string) => ['documents', 'search', query] as const,
  categories: ['documents', 'categories'] as const,
  categoryStats: (path?: string) =>
    ['documents', 'category-stats', path] as const,
  syncStatuses: ['documents', 'sync-statuses'] as const,
  syncStatus: (path: string) => ['documents', 'sync-status', path] as const,
};

// ==============================================================================
// Queries
// ==============================================================================

// NOTE: Fetches entire tree eagerly. Adequate for ~500 docs with 5min cache + virtual scrolling.
// For 1000+ docs, consider per-directory lazy loading with partial tree responses.
export const useDocumentTree = () => {
  const { data, isLoading, refetch, error } = useQuery({
    queryKey: QUERY_KEYS.tree,
    queryFn: documentsApi.getDocumentTree,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
  return { tree: data ?? [] as TreeNode[], loading: isLoading, refetch, error };
};

export const useDocumentStats = () => {
  const { data, isLoading, refetch, error } = useQuery({
    queryKey: QUERY_KEYS.stats,
    queryFn: documentsApi.getDocumentStats,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
  return { stats: data, loading: isLoading, refetch, error };
};

export const useDocument = (path: string | null) => {
  const { data, isLoading, refetch, error } = useQuery({
    queryKey: QUERY_KEYS.document(path || ''),
    queryFn: () => documentsApi.getDocument(path!),
    enabled: !!path,
    staleTime: 2 * 60 * 1000,
  });
  return {
    document: data,
    loading: isLoading,
    refetch,
    error: error ? documentsApi.getErrorMessage(error) : null,
  };
};

export const useSearchDocuments = (query: string, searchContent: boolean) => {
  return useQuery({
    queryKey: QUERY_KEYS.search(query),
    queryFn: () => documentsApi.searchDocuments(query, searchContent),
    enabled: query.length > 0,
    staleTime: 1 * 60 * 1000,
  });
};

export const useCategories = () => {
  return useQuery({
    queryKey: QUERY_KEYS.categories,
    queryFn: documentsApi.getCategories,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
};

export const useCategoryStats = (categoryPath?: string) => {
  return useQuery({
    queryKey: QUERY_KEYS.categoryStats(categoryPath),
    queryFn: () => documentsApi.getCategoryStats(categoryPath),
    staleTime: 5 * 60 * 1000,
  });
};

// ==============================================================================
// Mutations
// ==============================================================================

export const useCreateDocument = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ path, content }: CreateDocumentRequest) =>
      documentsApi.createDocument(path, content),
    onSuccess: (data) => {
      // Invalidate tree and stats
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats });

      // Set document in cache
      queryClient.setQueryData(QUERY_KEYS.document(data.path), data);

      toast({
        title: 'Document created',
        description: `Successfully created ${data.path}`,
      });
    },
    onError: (error) => {
      toast({
        title: 'Failed to create document',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useUpdateDocument = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      documentsApi.updateDocument(path, content),
    onMutate: async ({ path, content }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: QUERY_KEYS.document(path) });

      // Snapshot previous value
      const previousDocument = queryClient.getQueryData<Document>(
        QUERY_KEYS.document(path)
      );

      // Optimistically update
      if (previousDocument) {
        queryClient.setQueryData<Document>(QUERY_KEYS.document(path), {
          ...previousDocument,
          content,
        });
      }

      return { previousDocument };
    },
    onSuccess: (data, { path }) => {
      // Update cache with server response
      queryClient.setQueryData(QUERY_KEYS.document(path), data);

      // Invalidate stats (word count may have changed)
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats });

      toast({
        title: 'Document updated',
        description: `Successfully updated ${path}`,
      });
    },
    onError: (error, { path }, context) => {
      // Rollback on error
      if (context?.previousDocument) {
        queryClient.setQueryData(
          QUERY_KEYS.document(path),
          context.previousDocument
        );
      }

      toast({
        title: 'Failed to update document',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useDeleteDocument = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: documentsApi.deleteDocument,
    onSuccess: (data, path) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: QUERY_KEYS.document(path) });

      // Invalidate tree and stats
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats });

      toast({
        title: 'Document deleted',
        description: data.message,
      });
    },
    onError: (error) => {
      toast({
        title: 'Failed to delete document',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useCreateDirectory = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ path }: CreateDirectoryRequest) =>
      documentsApi.createDirectory(path),
    onSuccess: (data) => {
      // Invalidate tree and stats
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats });

      toast({
        title: 'Directory created',
        description: data.message,
      });
    },
    onError: (error) => {
      toast({
        title: 'Failed to create directory',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useDeleteDirectory = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: documentsApi.deleteDirectory,
    onSuccess: (data) => {
      // Invalidate tree and stats
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats });

      toast({
        title: 'Directory deleted',
        description: data.message,
      });
    },
    onError: (error) => {
      toast({
        title: 'Failed to delete directory',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useBulkDeleteDocuments = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ paths }: BulkDeleteRequest) =>
      documentsApi.bulkDeleteDocuments(paths),
    onSuccess: (data) => {
      // Invalidate tree and stats
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats });

      // Remove deleted documents from cache
      data.successful.forEach((path) => {
        queryClient.removeQueries({ queryKey: QUERY_KEYS.document(path) });
      });

      toast({
        title: 'Bulk delete completed',
        description: `${data.successful.length} documents deleted, ${data.failed.length} failed`,
      });
    },
    onError: (error) => {
      toast({
        title: 'Bulk delete failed',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useBulkMoveDocuments = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ paths, target_directory }: BulkMoveRequest) =>
      documentsApi.bulkMoveDocuments(paths, target_directory),
    onSuccess: (data) => {
      // Invalidate tree and stats
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats });

      // Invalidate moved documents
      data.successful.forEach((path) => {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.document(path) });
      });

      toast({
        title: 'Bulk move completed',
        description: `${data.successful.length} documents moved, ${data.failed.length} failed`,
      });
    },
    onError: (error) => {
      toast({
        title: 'Bulk move failed',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

// ==============================================================================
// Sync Status Queries
// ==============================================================================

export const useSyncStatuses = () => {
  return useQuery({
    queryKey: QUERY_KEYS.syncStatuses,
    queryFn: documentsApi.getAllSyncStatuses,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
};

export const useSyncStatus = (path: string | null) => {
  return useQuery({
    queryKey: QUERY_KEYS.syncStatus(path || ''),
    queryFn: () => documentsApi.getSyncStatus(path!),
    enabled: !!path,
    staleTime: 30 * 1000,
  });
};

// ==============================================================================
// Sync Mutations
// ==============================================================================

export const useReindexDocument = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (path: string) => documentsApi.reindexDocument(path),
    onSuccess: (_data, path) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.syncStatuses });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.syncStatus(path) });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.document(path) });
      toast({
        title: 'Re-index complete',
        description: `Successfully re-indexed ${path}`,
      });
    },
    onError: (error) => {
      toast({
        title: 'Re-index failed',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useReindexDirectory = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (path: string) => documentsApi.reindexDirectory(path),
    onSuccess: (data, path) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.syncStatuses });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree });
      toast({
        title: 'Directory re-index complete',
        description: `Re-indexed ${data.length} documents in ${path}`,
      });
    },
    onError: (error) => {
      toast({
        title: 'Directory re-index failed',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useReindexAll = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => documentsApi.reindexAll(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      toast({
        title: 'Full re-index complete',
        description: `Re-indexed ${data.length} documents`,
      });
    },
    onError: (error) => {
      toast({
        title: 'Full re-index failed',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

export const useResolveConflict = () => {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ path, resolution }: { path: string; resolution: ConflictResolution }) =>
      documentsApi.resolveConflict(path, resolution),
    onSuccess: (data, { path }) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.syncStatuses });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.syncStatus(path) });
      queryClient.setQueryData(QUERY_KEYS.document(path), data);
      toast({
        title: 'Conflict resolved',
        description: `Successfully resolved conflict for ${path}`,
      });
    },
    onError: (error) => {
      toast({
        title: 'Conflict resolution failed',
        description: documentsApi.getErrorMessage(error),
        variant: 'destructive',
      });
    },
  });
};

// ==============================================================================
// Cache Management
// ==============================================================================

export const useInvalidateDocuments = () => {
  const queryClient = useQueryClient();

  return {
    invalidateTree: () =>
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.tree }),
    invalidateStats: () =>
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.stats }),
    invalidateDocument: (path: string) =>
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.document(path) }),
    invalidateSyncStatuses: () =>
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.syncStatuses }),
    invalidateSyncStatus: (path: string) =>
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.syncStatus(path) }),
    invalidateAll: () =>
      queryClient.invalidateQueries({ queryKey: ['documents'] }),
  };
};
