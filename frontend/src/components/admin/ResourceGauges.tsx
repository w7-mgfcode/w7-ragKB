import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from '@/components/ui/tooltip';
import type { SystemResources } from '@/types/systemMonitor';

interface ResourceGaugesProps {
  resources: SystemResources;
}

function safePercent(used: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(Math.round((used / total) * 100), 100);
}

export default function ResourceGauges({ resources }: ResourceGaugesProps) {
  const memoryPercent = safePercent(resources.system_memory_used_mb, resources.system_memory_total_mb);
  const diskPercent = safePercent(resources.disk_used_gb, resources.disk_total_gb);
  const cpuPercent = Math.min(Math.round(resources.cpu_percent), 100);

  const gauges = [
    {
      label: 'CPU',
      value: cpuPercent,
      tooltip: `${resources.cpu_percent.toFixed(1)}%`,
    },
    {
      label: 'Memory',
      value: memoryPercent,
      tooltip: `${resources.system_memory_used_mb.toFixed(0)} MB / ${resources.system_memory_total_mb.toFixed(0)} MB (${resources.system_memory_available_mb.toFixed(0)} MB available)`,
    },
    {
      label: 'Disk',
      value: diskPercent,
      tooltip: `${resources.disk_used_gb.toFixed(1)} GB / ${resources.disk_total_gb.toFixed(1)} GB (${resources.disk_free_gb.toFixed(1)} GB free)`,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">System Resources</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <TooltipProvider>
          {gauges.map((gauge) => (
            <div key={gauge.label} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{gauge.label}</span>
                <span className="font-medium">{gauge.value}%</span>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div>
                    <Progress value={gauge.value} />
                  </div>
                </TooltipTrigger>
                <TooltipContent>{gauge.tooltip}</TooltipContent>
              </Tooltip>
            </div>
          ))}
        </TooltipProvider>

        <div className="pt-2 text-sm text-muted-foreground">
          Process memory: {resources.process_memory_mb.toFixed(1)} MB
        </div>
      </CardContent>
    </Card>
  );
}
