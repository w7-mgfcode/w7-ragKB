/**
 * Sync status badge with color, icon, and tooltip.
 *
 * Displays the current sync status of a document as a compact badge
 * with appropriate color coding and accessibility support.
 */

import React from 'react';
import {
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  XCircle,
  Clock,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { SyncStatus } from '@/types/documents';

interface SyncStatusBadgeProps {
  status: SyncStatus;
  errorMessage?: string | null;
  size?: 'sm' | 'md';
}

const STATUS_CONFIG: Record<
  SyncStatus,
  { label: string; color: string; icon: React.ElementType }
> = {
  in_sync: {
    label: 'In Sync',
    color: 'text-green-500',
    icon: CheckCircle,
  },
  out_of_sync: {
    label: 'Out of Sync',
    color: 'text-yellow-500',
    icon: AlertTriangle,
  },
  processing: {
    label: 'Processing',
    color: 'text-blue-500',
    icon: RefreshCw,
  },
  error: {
    label: 'Error',
    color: 'text-red-500',
    icon: XCircle,
  },
  orphaned_chunks: {
    label: 'Orphaned',
    color: 'text-orange-500',
    icon: AlertTriangle,
  },
  pending_indexing: {
    label: 'Pending',
    color: 'text-muted-foreground',
    icon: Clock,
  },
};

export const SyncStatusBadge: React.FC<SyncStatusBadgeProps> = ({
  status,
  errorMessage,
  size = 'sm',
}) => {
  const config = STATUS_CONFIG[status];
  if (!config) return null;

  const Icon = config.icon;
  const iconSize = size === 'sm' ? 12 : 16;
  const isProcessing = status === 'processing';

  const tooltipText =
    status === 'error' && errorMessage
      ? `${config.label}: ${errorMessage}`
      : config.label;

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              'inline-flex items-center gap-1 shrink-0',
              config.color,
            )}
            role="status"
            aria-label={tooltipText}
          >
            <Icon
              size={iconSize}
              className={isProcessing ? 'animate-spin' : undefined}
              aria-hidden="true"
            />
            {size === 'md' && (
              <span className="text-xs font-medium">{config.label}</span>
            )}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <p className="text-xs">{tooltipText}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
