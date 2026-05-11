import { useState, useEffect } from 'react';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { Skeleton } from '@/components/ui/skeleton';
import { MarkdownRenderer } from './MarkdownRenderer';
import { fetchDocument } from '@/lib/documents-api';

interface DocumentPreviewProps {
  path: string;
  children: React.ReactNode;
}

// Module-level cache persists across renders
const previewCache = new Map<string, string>();

export const DocumentPreview = ({ path, children }: DocumentPreviewProps) => {
  const [content, setContent] = useState<string | null>(previewCache.get(path) ?? null);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen || previewCache.has(path)) {
      if (previewCache.has(path)) setContent(previewCache.get(path)!);
      return;
    }

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const doc = await fetchDocument(path);
        // Take first ~200 words
        const words = doc.content.split(/\s+/);
        const preview = words.length > 200
          ? words.slice(0, 200).join(' ') + '...'
          : doc.content;
        previewCache.set(path, preview);
        if (!cancelled) setContent(preview);
      } catch {
        if (!cancelled) setContent('Failed to load preview');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [isOpen, path]);

  return (
    <HoverCard openDelay={500} closeDelay={200} onOpenChange={setIsOpen}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent className="w-96 max-h-64 overflow-auto">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : content ? (
          <MarkdownRenderer content={content} className="text-xs" />
        ) : null}
      </HoverCardContent>
    </HoverCard>
  );
};
