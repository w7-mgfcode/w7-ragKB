import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { createDocument } from '@/lib/documents-api';

interface CreateDocumentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPath: string;
  onCreated: () => void;
}

const FILENAME_RE = /^[a-zA-Z0-9_-]+\.md$/;

export const CreateDocumentDialog = ({
  open,
  onOpenChange,
  currentPath,
  onCreated,
}: CreateDocumentDialogProps) => {
  const [filename, setFilename] = useState('');
  const [content, setContent] = useState('# New Document\n\n');
  const [creating, setCreating] = useState(false);
  const [filenameError, setFilenameError] = useState('');

  const validateFilename = (name: string) => {
    if (!name) {
      setFilenameError('Filename is required');
      return false;
    }
    if (!FILENAME_RE.test(name)) {
      setFilenameError('Use only letters, numbers, hyphens, underscores. Must end with .md');
      return false;
    }
    setFilenameError('');
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateFilename(filename)) return;

    try {
      setCreating(true);
      const fullPath = currentPath ? `${currentPath}/${filename}` : filename;
      await createDocument(fullPath, content);
      toast.success('Document created', { description: filename });
      setFilename('');
      setContent('# New Document\n\n');
      onOpenChange(false);
      onCreated();
    } catch (err) {
      toast.error('Failed to create document', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Create Document</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="doc-path">Directory</Label>
            <Input id="doc-path" value={currentPath || '(root)'} disabled />
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-filename">Filename</Label>
            <Input
              id="doc-filename"
              placeholder="my-document.md"
              value={filename}
              onChange={(e) => {
                setFilename(e.target.value);
                if (filenameError) validateFilename(e.target.value);
              }}
            />
            {filenameError && <p className="text-sm text-destructive">{filenameError}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-content">Content</Label>
            <Textarea
              id="doc-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="font-mono text-sm min-h-[200px]"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={creating}>
              {creating ? 'Creating...' : 'Create'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};
