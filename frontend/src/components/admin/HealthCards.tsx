import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Activity, Database, Server, FileText } from 'lucide-react';
import type { ServiceHealth } from '@/types/systemMonitor';

interface HealthCardsProps {
  services: ServiceHealth[];
  uptimeSeconds: number;
}

const SERVICE_ICONS: Record<string, React.ReactNode> = {
  'Slack bot': <Activity className="h-5 w-5" />,
  'Database pool': <Database className="h-5 w-5" />,
  'HTTP server': <Server className="h-5 w-5" />,
  'RAG pipeline': <FileText className="h-5 w-5" />,
};

function statusBadge(status: ServiceHealth['status']) {
  switch (status) {
    case 'healthy':
      return <Badge className="bg-green-500 text-white border-green-500">healthy</Badge>;
    case 'degraded':
      return <Badge variant="secondary" className="bg-yellow-500 text-white border-yellow-500">degraded</Badge>;
    case 'down':
      return <Badge variant="destructive">down</Badge>;
  }
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  parts.push(`${minutes}m`);
  return parts.join(' ');
}

export default function HealthCards({ services, uptimeSeconds }: HealthCardsProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {services.map((service) => (
        <Card key={service.name}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              {SERVICE_ICONS[service.name] ?? <Server className="h-5 w-5" />}
              {service.name}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-2">
              {statusBadge(service.status)}
              {service.details && (
                <p className="text-xs text-muted-foreground">{service.details}</p>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Uptime</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg font-semibold">{formatUptime(uptimeSeconds)}</p>
        </CardContent>
      </Card>
    </div>
  );
}
