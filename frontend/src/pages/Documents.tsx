import { useState, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { MessageSquare, Plus, FolderPlus } from 'lucide-react';
import { toast } from 'sonner';

import {
  useDocumentTree,
  useDocumentStats,
  useDocument,
  useSyncStatuses,
  useSyncStatus,
  useReindexDocument,
} from '@/hooks/useDocuments';
import { useDocumentWebSocket } from '@/hooks/useDocumentWebSocket';
import { deleteDocument, bulkDeleteDocuments, bulkMoveDocuments } from '@/lib/documents-api';
import { updateDocument, reindexDocument } from '@/lib/documents-api';

import { StatsPanel } from '@/components/documents/StatsPanel';
import { SearchBar } from '@/components/documents/SearchBar';
import { DocumentTree } from '@/components/documents/DocumentTree';
import { DocumentViewer } from '@/components/documents/DocumentViewer';
import { DocumentEditor } from '@/components/documents/DocumentEditor';
import { BulkActionsToolbar } from '@/components/documents/BulkActionsToolbar';
import { CreateDocumentDialog } from '@/components/documents/CreateDocumentDialog';
import { ReindexDialog } from '@/components/documents/ReindexDialog';

import type { TreeNode, DocumentSyncInfo } from '@/types/documents';

type ViewMode = 'browse' | 'view' | 'edit';

const collectDirectories = (nodes: TreeNode[], prefix = ''): string[] => {
  const dirs: string[] = [];
  for (const node of nodes) {
    if (node.type === 'directory') {
      dirs.push(node.path);
      if (node.children) {
        dirs.push(...collectDirectories(node.children, node.path));
      }
    }
  }
  return dirs;
};

export const Documents = () => {
  const { tree, loading: treeLoading, refetch: refetchTree } = useDocumentTree();
  const { stats, loading: statsLoading, refetch: refetchStats } = useDocumentStats();
  const { data: syncStatusList } = useSyncStatuses();

  // WebSocket for real-time cache invalidation
  useDocumentWebSocket(true);

  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('browse');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [currentDirPath, setCurrentDirPath] = useState('');
  const [reindexTarget, setReindexTarget] = useState<{ type: 'document' | 'directory' | 'all'; path?: string } | null>(null);

  const { document: currentDoc, loading: docLoading, error: docError, refetch: refetchDoc } = useDocument(
    viewMode !== 'browse' ? selectedPath : null
  );

  const directories = useMemo(() => collectDirectories(tree), [tree]);

  // Build a record keyed by file_path for fast lookup
  const syncStatuses = useMemo(() => {
    const map: Record<string, DocumentSyncInfo> = {};
    if (syncStatusList) {
      for (const info of syncStatusList) {
        map[info.file_path] = info;
      }
    }
    return map;
  }, [syncStatusList]);

  // Get sync info for the currently viewed document
  const currentSyncInfo = selectedPath ? syncStatuses[selectedPath] : undefined;

  const handleSelectDocument = useCallback((path: string) => {
    setSelectedPath(path);
    setViewMode('view');
  }, []);

  const handleClose = useCallback(() => {
    setSelectedPath(null);
    setViewMode('browse');
  }, []);

  const handleEdit = useCallback(() => {
    setViewMode('edit');
  }, []);

  const handleSave = useCallback(async (content: string) => {
    if (!selectedPath) return;
    await updateDocument(selectedPath, content);
    toast.success('Document saved');
    refetchDoc();
    refetchTree();
    refetchStats();
    setViewMode('view');
  }, [selectedPath, refetchDoc, refetchTree, refetchStats]);

  const handleCancelEdit = useCallback(() => {
    setViewMode('view');
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!selectedPath) return;
    try {
      await deleteDocument(selectedPath);
      toast.success('Document deleted');
      setDeleteDialogOpen(false);
      handleClose();
      refetchTree();
      refetchStats();
    } catch (err) {
      toast.error('Failed to delete', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  }, [selectedPath, handleClose, refetchTree, refetchStats]);

  const handleToggleSelect = useCallback((path: string) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleBulkDelete = useCallback(async () => {
    const result = await bulkDeleteDocuments(Array.from(selectedPaths));
    refetchTree();
    refetchStats();
    return result;
  }, [selectedPaths, refetchTree, refetchStats]);

  const handleBulkMove = useCallback(async (target: string) => {
    const targetDir = target === '__root__' ? '' : target;
    const result = await bulkMoveDocuments(Array.from(selectedPaths), targetDir);
    refetchTree();
    refetchStats();
    return result;
  }, [selectedPaths, refetchTree, refetchStats]);

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
  }, []);

  const handleBulkReindex = useCallback(async () => {
    const paths = Array.from(selectedPaths);
    for (const path of paths) {
      await reindexDocument(path);
    }
  }, [selectedPaths]);

  const handleCreated = useCallback(() => {
    refetchTree();
    refetchStats();
  }, [refetchTree, refetchStats]);

  return (
    <div className="flex flex-col min-h-screen">
      <a href="#document-tree" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:p-4 focus:bg-background focus:text-foreground focus:border">
        Skip to document tree
      </a>
      {/* Header */}
      <div className="border-b">
        <div className="flex items-center justify-between px-4 py-2">
          <h1 className="text-lg font-semibold">Documents</h1>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New Document
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/">
                <MessageSquare className="mr-2 h-4 w-4" />
                Back to Chat
              </Link>
            </Button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="p-4 border-b">
        <StatsPanel stats={stats} loading={statsLoading} />
      </div>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — tree */}
        <div className={`${viewMode === 'browse' ? 'flex' : 'hidden md:flex'} flex-col w-full md:w-80 border-r`}>
          <div className="p-4">
            <SearchBar value={searchQuery} onChange={setSearchQuery} onSearch={handleSearch} />
          </div>
          <Separator />
          <ScrollArea id="document-tree" className="flex-1">
            <DocumentTree
              nodes={tree}
              selectedPath={selectedPath}
              onSelect={handleSelectDocument}
              searchQuery={searchQuery}
              selectedPaths={selectedPaths}
              onToggleSelect={handleToggleSelect}
              syncStatuses={syncStatuses}
            />
          </ScrollArea>
          <BulkActionsToolbar
            selectedPaths={Array.from(selectedPaths)}
            onBulkDelete={handleBulkDelete}
            onBulkMove={handleBulkMove}
            onBulkReindex={handleBulkReindex}
            onClearSelection={() => setSelectedPaths(new Set())}
            directories={directories}
          />
        </div>

        {/* Right panel — viewer or editor */}
        <div className={`${viewMode === 'browse' ? 'hidden md:flex' : 'flex'} flex-col flex-1 overflow-hidden`}>
          {viewMode === 'edit' && currentDoc ? (
            <DocumentEditor
              document={currentDoc}
              onSave={handleSave}
              onCancel={handleCancelEdit}
            />
          ) : (
            <DocumentViewer
              document={currentDoc}
              loading={docLoading}
              error={docError}
              onEdit={handleEdit}
              onDelete={() => setDeleteDialogOpen(true)}
              onClose={handleClose}
              onRetry={refetchDoc}
              syncInfo={currentSyncInfo}
              onReindex={selectedPath ? () => setReindexTarget({ type: 'document', path: selectedPath }) : undefined}
            />
          )}
        </div>
      </div>

      {/* Create dialog */}
      <CreateDocumentDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        currentPath={currentDirPath}
        onCreated={handleCreated}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete document?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete "{selectedPath}" and its database records.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteConfirm} className="bg-destructive text-destructive-foreground">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Re-index dialog */}
      {reindexTarget && (
        <ReindexDialog
          open={!!reindexTarget}
          onOpenChange={(open) => { if (!open) setReindexTarget(null); }}
          target={reindexTarget}
          onComplete={() => {
            setReindexTarget(null);
            refetchTree();
            refetchStats();
          }}
        />
      )}
    </div>
  );
};

export default Documents;
