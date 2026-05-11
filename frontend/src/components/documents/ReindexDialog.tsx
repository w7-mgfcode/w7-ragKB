/**
 * Dialog for triggering document re-indexing.
 *
 * Shows what will be re-indexed, provides a confirmation button,
 * and displays progress and results.
 */

import React, { useState } from 'react';
import { RefreshCw, Loader2, CheckCircle, XCircle } from 'lucide-react';
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
import * as documentsApi from '@/lib/documents-api';
import type { DocumentSyncInfo } from '@/types/documents';

interface ReindexTarget {
  type: 'document' | 'directory' | 'all';
  path?: string;
}

interface ReindexDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  target: ReindexTarget;
  onComplete: () => void;
}

type Phase = 'confirm' | 'running' | 'done';

export const ReindexDialog: React.FC<ReindexDialogProps> = ({
  open,
  onOpenChange,
  target,
  onComplete,
}) => {
  const [phase, setPhase] = useState<Phase>('confirm');
  const [results, setResults] = useState<DocumentSyncInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  const targetLabel =
    target.type === 'all'
      ? 'all documents'
      : target.type === 'directory'
        ? `directory "${target.path}"`
        : `"${target.path}"`;

  const handleReindex = async () => {
    setPhase('running');
    setError(null);
    try {
      let result: DocumentSyncInfo | DocumentSyncInfo[];
      if (target.type === 'all') {
        result = await documentsApi.reindexAll();
      } else if (target.type === 'directory') {
        result = await documentsApi.reindexDirectory(target.path!);
      } else {
        result = await documentsApi.reindexDocument(target.path!);
      }
      setResults(Array.isArray(result) ? result : [result]);
      setPhase('done');
    } catch (err) {
      setError(documentsApi.getErrorMessage(err));
      setPhase('done');
    }
  };

  const handleClose = () => {
    if (phase === 'done') {
      onComplete();
    }
    onOpenChange(false);
    // Reset state after close animation
    setTimeout(() => {
      setPhase('confirm');
      setResults([]);
      setError(null);
    }, 200);
  };

  return (
    <AlertDialog open={open} onOpenChange={handleClose}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <RefreshCw size={18} />
            Re-index Documents
          </AlertDialogTitle>
          <AlertDialogDescription>
            {phase === 'confirm' && (
              <>
                This will re-chunk and re-embed {targetLabel}. This may take a
                moment for large documents.
              </>
            )}
            {phase === 'running' && (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Re-indexing {targetLabel}...
              </span>
            )}
            {phase === 'done' && error && (
              <span className="flex items-center gap-2 text-destructive">
                <XCircle size={16} />
                {error}
              </span>
            )}
            {phase === 'done' && !error && (
              <span className="flex items-center gap-2 text-green-500">
                <CheckCircle size={16} />
                Successfully re-indexed {results.length} document
                {results.length !== 1 ? 's' : ''}.
              </span>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          {phase === 'confirm' && (
            <>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleReindex}>
                Re-index
              </AlertDialogAction>
            </>
          )}
          {phase === 'running' && (
            <AlertDialogCancel disabled>Please wait...</AlertDialogCancel>
          )}
          {phase === 'done' && (
            <AlertDialogAction onClick={handleClose}>Done</AlertDialogAction>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};
