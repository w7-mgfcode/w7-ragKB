import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Trash2, FolderInput, X, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import type { BulkOperationResult } from '@/types/documents';

interface BulkActionsToolbarProps {
  selectedPaths: string[];
  onBulkDelete: () => Promise<BulkOperationResult>;
  onBulkMove: (target: string) => Promise<BulkOperationResult>;
  onBulkReindex?: () => Promise<void>;
  onClearSelection: () => void;
  directories: string[];
}

export const BulkActionsToolbar = ({
  selectedPaths,
  onBulkDelete,
  onBulkMove,
  onBulkReindex,
  onClearSelection,
  directories,
}: BulkActionsToolbarProps) => {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showMoveDialog, setShowMoveDialog] = useState(false);
  const [moveTarget, setMoveTarget] = useState('');
  const [operating, setOperating] = useState(false);

  if (selectedPaths.length === 0) return null;

  const handleDelete = async () => {
    try {
      setOperating(true);
      const result = await onBulkDelete();
      setShowDeleteDialog(false);
      if (result.failed.length > 0) {
        toast.error(`Deleted ${result.successful.length}, failed ${result.failed.length}`, {
          description: result.failed.map((e) => e.error).join('; '),
        });
      } else {
        toast.success(`Deleted ${result.successful.length} documents`);
      }
      onClearSelection();
    } catch (err) {
      toast.error('Bulk delete failed', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setOperating(false);
    }
  };

  const handleMove = async () => {
    if (!moveTarget) return;
    try {
      setOperating(true);
      const result = await onBulkMove(moveTarget);
      setShowMoveDialog(false);
      if (result.failed.length > 0) {
        toast.error(`Moved ${result.successful.length}, failed ${result.failed.length}`, {
          description: result.failed.map((e) => e.error).join('; '),
        });
      } else {
        toast.success(`Moved ${result.successful.length} documents to ${moveTarget}`);
      }
      onClearSelection();
    } catch (err) {
      toast.error('Bulk move failed', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setOperating(false);
      setMoveTarget('');
    }
  };

  return (
    <>
      <div role="toolbar" aria-label="Bulk actions" className="flex items-center gap-2 p-3 border-t bg-muted/50">
        <Badge variant="secondary">{selectedPaths.length} selected</Badge>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => setShowDeleteDialog(true)}
          disabled={operating}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Delete
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowMoveDialog(true)}
          disabled={operating}
        >
          <FolderInput className="mr-2 h-4 w-4" />
          Move
        </Button>
        {onBulkReindex && (
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              setOperating(true);
              try {
                await onBulkReindex();
                toast.success(`Re-indexed ${selectedPaths.length} documents`);
              } catch (err) {
                toast.error('Re-index failed', {
                  description: err instanceof Error ? err.message : 'Unknown error',
                });
              } finally {
                setOperating(false);
              }
            }}
            disabled={operating}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Re-index
          </Button>
        )}
        <div className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onClearSelection}>
          <X className="mr-2 h-4 w-4" />
          Clear
        </Button>
      </div>

      {/* Delete confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selectedPaths.length} documents?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The documents and their database records will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={operating}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={operating}
              className="bg-destructive text-destructive-foreground"
            >
              {operating ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Move dialog */}
      <Dialog open={showMoveDialog} onOpenChange={setShowMoveDialog}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Move {selectedPaths.length} documents</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Select value={moveTarget} onValueChange={setMoveTarget}>
              <SelectTrigger>
                <SelectValue placeholder="Select target directory" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__root__">(root)</SelectItem>
                {directories.map((dir) => (
                  <SelectItem key={dir} value={dir}>{dir}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowMoveDialog(false)} disabled={operating}>
              Cancel
            </Button>
            <Button onClick={handleMove} disabled={!moveTarget || operating}>
              {operating ? 'Moving...' : 'Move'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};
