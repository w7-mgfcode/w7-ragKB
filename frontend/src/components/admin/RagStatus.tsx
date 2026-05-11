import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { RagStatus } from '@/types/systemMonitor';

interface RagStatusPanelProps {
  status: RagStatus;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return 'Never';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function RagStatusPanel({ status }: RagStatusPanelProps) {
  const isEmpty = status.total_documents === 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">RAG Pipeline</CardTitle>
      </CardHeader>
      <CardContent>
        {isEmpty ? (
          <p className="text-sm text-muted-foreground">No documents indexed</p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Documents</span>
              <Badge variant="secondary">{status.total_documents.toLocaleString()}</Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Chunks</span>
              <Badge variant="secondary">{status.total_chunks.toLocaleString()}</Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Last indexed</span>
              <span className="text-xs">{formatTimestamp(status.last_indexed_at)}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
