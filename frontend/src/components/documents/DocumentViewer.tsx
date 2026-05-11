/**
 * Document viewer component for displaying markdown content.
 * 
 * Renders markdown with syntax highlighting and displays metadata.
 * Provides actions for editing and deleting documents.
 */

import React from 'react';
import { Edit, Trash2, X, Clock, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { SyncStatusBadge } from './SyncStatusBadge';
import type { Document, DocumentSyncInfo } from '@/types/documents';

interface DocumentViewerProps {
  document: Document | undefined;
  loading: boolean;
  error: string | null;
  onEdit: () => void;
  onDelete: () => void;
  onClose: () => void;
  onRetry?: () => void;
  syncInfo?: DocumentSyncInfo;
  onReindex?: () => void;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  document,
  loading,
  error,
  onEdit,
  onDelete,
  onClose,
  onRetry,
  syncInfo,
  onReindex,
}) => {
  if (loading) {
    return (
      <Card className="h-full">
        <CardHeader>
          <div className="h-6 bg-muted animate-pulse rounded w-1/3" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-4 bg-muted animate-pulse rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="h-full flex items-center justify-center">
        <CardContent className="text-center space-y-2" role="alert">
          <p className="text-destructive">{error}</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              Retry
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  if (!document) {
    return (
      <Card className="h-full flex items-center justify-center">
        <CardContent>
          <p className="text-muted-foreground">Select a document to view</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <CardTitle className="text-lg">{getFileName(document.path)}</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">{document.path}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onEdit}>
              <Edit className="h-4 w-4 mr-2" />
              Edit
            </Button>
            <Button variant="outline" size="sm" onClick={onDelete}>
              <Trash2 className="h-4 w-4 mr-2" />
              Delete
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close viewer">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-4 mt-4">
          {syncInfo && (
            <SyncStatusBadge
              status={syncInfo.sync_status}
              errorMessage={syncInfo.error_message}
              size="md"
            />
          )}
          <Badge variant="secondary" className="flex items-center gap-1">
            <FileText className="h-3 w-3" />
            {formatFileSize(document.metadata.size)}
          </Badge>
          <Badge variant="secondary" className="flex items-center gap-1">
            <FileText className="h-3 w-3" />
            {document.metadata.word_count} words
          </Badge>
          <Badge variant="secondary" className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatTimestamp(document.metadata.modified)}
          </Badge>
        </div>
      </CardHeader>

      <Separator />

      <CardContent className="flex-1 overflow-auto pt-6">
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ node, inline, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                return !inline && match ? (
                  <SyntaxHighlighter
                    style={vscDarkPlus}
                    language={match[1]}
                    PreTag="div"
                    {...props}
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {document.content}
          </ReactMarkdown>
        </div>
      </CardContent>
    </Card>
  );
};

// Utility functions
const getFileName = (path: string): string => {
  return path.split('/').pop() || path;
};

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatTimestamp = (timestamp: string): string => {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min${diffMins > 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
};
