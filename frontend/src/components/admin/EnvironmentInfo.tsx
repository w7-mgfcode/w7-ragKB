import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableRow, TableCell } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import type { EnvironmentInfo } from '@/types/systemMonitor';

interface EnvironmentInfoPanelProps {
  info: EnvironmentInfo;
}

export default function EnvironmentInfoPanel({ info }: EnvironmentInfoPanelProps) {
  const configEntries = Object.entries(info.config);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Environment</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm">
          <span className="text-muted-foreground">Python </span>
          <span className="font-medium">{info.python_version}</span>
        </p>

        <Table>
          <TableBody>
            {info.dependencies.map((dep) => (
              <TableRow key={dep.name}>
                <TableCell className="font-medium text-muted-foreground">{dep.name}</TableCell>
                <TableCell className="text-right">
                  <Badge variant="outline">{dep.version}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {configEntries.length > 0 && (
          <>
            <Separator />
            <div className="space-y-2">
              {configEntries.map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground font-mono text-xs">{key}</span>
                  <span>{value}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
