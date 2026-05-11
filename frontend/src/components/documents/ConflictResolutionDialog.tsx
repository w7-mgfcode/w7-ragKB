/**
 * Dialog for resolving document sync conflicts.
 *
 * Shows side-by-side comparison of filesystem vs database content
 * with three resolution strategies: keep filesystem, keep database, or manual merge.
 */

import React, { useState } from 'react';
import { FileText, Database, Merge, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import type { ConflictInfo, ConflictResolution } from '@/types/documents';

interface ConflictResolutionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conflict: ConflictInfo;
  onResolve: (resolution: ConflictResolution) => Promise<void>;
}

export const ConflictResolutionDialog: React.FC<ConflictResolutionDialogProps> = ({
  open,
  onOpenChange,
  conflict,
  onResolve,
}) => {
  const [isResolving, setIsResolving] = useState(false);
  const [showMerge, setShowMerge] = useState(false);
  const [mergedContent, setMergedContent] = useState('');

  const handleResolve = async (strategy: ConflictResolution['strategy']) => {
    setIsResolving(true);
    try {
      const resolution: ConflictResolution = { strategy };
      if (strategy === 'manual_merge') {
        resolution.merged_content = mergedContent;
      }
      await onResolve(resolution);
      onOpenChange(false);
      setShowMerge(false);
    } finally {
      setIsResolving(false);
    }
  };

  const fsDate = new Date(conflict.filesystem_mtime);
  const dbDate = new Date(conflict.database_mtime);
  const fsNewer = fsDate > dbDate;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Resolve Conflict</DialogTitle>
          <DialogDescription>
            {conflict.file_path} has conflicting versions.
            Type: {conflict.conflict_type.replace(/_/g, ' ')}
          </DialogDescription>
        </DialogHeader>

        {showMerge ? (
          <div className="flex-1 min-h-0 space-y-2">
            <p className="text-sm text-muted-foreground">
              Edit the merged content below, then click "Save Merge".
            </p>
            <Textarea
              value={mergedContent}
              onChange={(e) => setMergedContent(e.target.value)}
              className="font-mono text-xs min-h-[300px] resize-y"
              aria-label="Merged content"
            />
          </div>
        ) : (
          <div className="flex-1 min-h-0 grid grid-cols-2 gap-4">
            <div className="flex flex-col min-h-0">
              <div className="flex items-center gap-2 mb-2">
                <FileText size={16} className="text-blue-500" />
                <span className="text-sm font-medium">Filesystem</span>
                {fsNewer && (
                  <span className="text-xs text-green-500">(newer)</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mb-1">
                Modified: {fsDate.toLocaleString()}
              </p>
              <ScrollArea className="flex-1 border rounded-md p-3 max-h-[300px]">
                <pre className="text-xs whitespace-pre-wrap font-mono">
                  {conflict.filesystem_content}
                </pre>
              </ScrollArea>
            </div>

            <div className="flex flex-col min-h-0">
              <div className="flex items-center gap-2 mb-2">
                <Database size={16} className="text-purple-500" />
                <span className="text-sm font-medium">Database</span>
                {!fsNewer && (
                  <span className="text-xs text-green-500">(newer)</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mb-1">
                Modified: {dbDate.toLocaleString()}
              </p>
              <ScrollArea className="flex-1 border rounded-md p-3 max-h-[300px]">
                <pre className="text-xs whitespace-pre-wrap font-mono">
                  {conflict.database_content}
                </pre>
              </ScrollArea>
            </div>
          </div>
        )}

        <Separator />

        <DialogFooter className="flex-shrink-0 gap-2 sm:gap-2">
          {showMerge ? (
            <>
              <Button
                variant="outline"
                onClick={() => setShowMerge(false)}
                disabled={isResolving}
              >
                Back
              </Button>
              <Button
                onClick={() => handleResolve('manual_merge')}
                disabled={isResolving || !mergedContent.trim()}
              >
                {isResolving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save Merge
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => handleResolve('keep_filesystem')}
                disabled={isResolving}
              >
                {isResolving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <FileText className="mr-1 h-4 w-4" />
                Keep Filesystem
              </Button>
              <Button
                variant="outline"
                onClick={() => handleResolve('keep_database')}
                disabled={isResolving}
              >
                {isResolving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <Database className="mr-1 h-4 w-4" />
                Keep Database
              </Button>
              <Button
                onClick={() => {
                  setMergedContent(conflict.filesystem_content);
                  setShowMerge(true);
                }}
                disabled={isResolving}
              >
                <Merge className="mr-1 h-4 w-4" />
                Manual Merge
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
