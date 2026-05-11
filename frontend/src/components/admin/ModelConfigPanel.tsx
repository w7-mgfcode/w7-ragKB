import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableRow, TableCell } from '@/components/ui/table';
import type { ModelConfig } from '@/types/systemMonitor';

interface ModelConfigPanelProps {
  config: ModelConfig;
}

export default function ModelConfigPanel({ config }: ModelConfigPanelProps) {
  const rows = [
    { label: 'LLM Model', value: config.llm_model },
    { label: 'Embedding Model', value: config.embedding_model },
    { label: 'Embedding Dimensions', value: String(config.embedding_dimensions) },
    { label: 'GCP Project', value: config.gcp_project ?? '—' },
    { label: 'GCP Region', value: config.gcp_region },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Model Configuration</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.label}>
                <TableCell className="font-medium text-muted-foreground">{row.label}</TableCell>
                <TableCell>{row.value}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
