/**
 * Document editor component with markdown editing.
 *
 * Provides a textarea for editing markdown content with save/cancel actions,
 * dirty state tracking, and unsaved changes warning.
 */

import React, { useState, useEffect } from 'react';
import { Save, X, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import type { Document } from '@/types/documents';

interface DocumentEditorProps {
  document: Document | undefined;
  onSave: (content: string) => void;
  onCancel: () => void;
}

export const DocumentEditor: React.FC<DocumentEditorProps> = ({
  document: doc,
  onSave,
  onCancel,
}) => {
  const [content, setContent] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Initialize content when document loads
  useEffect(() => {
    if (doc) {
      setContent(doc.content);
      setIsDirty(false);
    }
  }, [doc]);

  // Save to localStorage on content change (for recovery)
  useEffect(() => {
    if (isDirty && doc) {
      const recoveryKey = `document-recovery-${doc.path}`;
      localStorage.setItem(recoveryKey, content);
    }
  }, [content, isDirty, doc]);

  // Check for unsaved changes on unmount
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value);
    setIsDirty(e.target.value !== doc?.content);
  };

  const handleSave = async () => {
    if (doc) {
      setIsSaving(true);
      try {
        await onSave(content);
        setIsDirty(false);
        // Clear recovery data
        const recoveryKey = `document-recovery-${doc.path}`;
        localStorage.removeItem(recoveryKey);
      } finally {
        setIsSaving(false);
      }
    }
  };

  const handleCancel = () => {
    if (isDirty) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to cancel?'
      );
      if (!confirmed) return;
    }

    if (doc) {
      const recoveryKey = `document-recovery-${doc.path}`;
      localStorage.removeItem(recoveryKey);
    }

    onCancel();
  };

  // Check for recovery data on mount
  useEffect(() => {
    if (doc) {
      const recoveryKey = `document-recovery-${doc.path}`;
      const recoveredContent = localStorage.getItem(recoveryKey);

      if (recoveredContent && recoveredContent !== doc.content) {
        const shouldRecover = window.confirm(
          'Found unsaved changes from a previous session. Would you like to recover them?'
        );

        if (shouldRecover) {
          setContent(recoveredContent);
          setIsDirty(true);
        } else {
          localStorage.removeItem(recoveryKey);
        }
      }
    }
  }, [doc]);

  if (!doc) {
    return (
      <Card className="h-full flex items-center justify-center">
        <CardContent>
          <p className="text-muted-foreground">No document selected</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <CardTitle className="text-lg">
              Edit: {getFileName(doc.path)}
            </CardTitle>
            <p className="text-sm text-muted-foreground mt-1">{doc.path}</p>
          </div>
          <div className="flex items-center gap-2">
            {isDirty && (
              <Badge variant="outline" className="text-orange-500" role="status">
                Unsaved changes
              </Badge>
            )}
            {isSaving && (
              <Badge variant="outline" className="text-blue-500">
                Saving...
              </Badge>
            )}
            <Button
              variant="default"
              size="sm"
              onClick={handleSave}
              disabled={!isDirty || isSaving}
            >
              <Save className="h-4 w-4 mr-2" />
              Save
            </Button>
            <Button variant="outline" size="sm" onClick={handleCancel}>
              <X className="h-4 w-4 mr-2" />
              Cancel
            </Button>
          </div>
        </div>
      </CardHeader>

      <Separator />

      {isDirty && (
        <div className="px-6 pt-4">
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              You have unsaved changes. Press Ctrl+S to save or click the Save button.
            </AlertDescription>
          </Alert>
        </div>
      )}

      <CardContent className="flex-1 overflow-hidden pt-6">
        <Textarea
          value={content}
          onChange={handleContentChange}
          className="h-full font-mono text-sm resize-none"
          placeholder="Write your markdown content here..."
          onKeyDown={(e) => {
            // Ctrl+S to save
            if (e.ctrlKey && e.key === 's') {
              e.preventDefault();
              if (isDirty && !isSaving) {
                handleSave();
              }
            }
          }}
        />
      </CardContent>

      <div className="px-6 py-3 border-t">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{content.split(/\s+/).filter(Boolean).length} words</span>
          <span>{content.split('\n').length} lines</span>
          <span>{content.length} characters</span>
        </div>
      </div>
    </Card>
  );
};

// Utility functions
const getFileName = (path: string): string => {
  return path.split('/').pop() || path;
};
