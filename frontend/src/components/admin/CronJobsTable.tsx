/**
 * Cron Jobs Table Component
 * 
 * Displays and manages scheduled cron jobs for triggering agent actions.
 * Features:
 * - List all cron jobs with metadata
 * - Filter by enabled status
 * - Search by cron job ID
 * - Create/Edit/Delete cron jobs
 * - Pause/Resume cron jobs
 * - Execute cron jobs immediately
 * - View execution history
 */

import * as React from 'react';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  type VisibilityState,
} from '@tanstack/react-table';
import { ArrowUpDown, MoreHorizontal, Plus, Clock, Play, Pause, History, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useCronJobs } from '@/hooks/useGateway';
import type { CronJob } from '@/types/gateway';
import { CronJobDialog } from './CronJobDialog';
import { CronExecutionHistoryDrawer } from './CronExecutionHistoryDrawer';
import { deleteCronJob, pauseCronJob, resumeCronJob, executeCronJobNow } from '@/lib/api';
import { toast } from 'sonner';

export function CronJobsTable() {
  const [enabledFilter, setEnabledFilter] = React.useState<boolean | undefined>(undefined);
  const { cronJobs, loading, error, refetch } = useCronJobs(
    enabledFilter !== undefined ? { enabled: enabledFilter } : undefined
  );
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = React.useState({});
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [historyDrawerOpen, setHistoryDrawerOpen] = React.useState(false);
  const [selectedCronJob, setSelectedCronJob] = React.useState<CronJob | null>(null);

  const handlePauseResume = async (cronJob: CronJob) => {
    try {
      if (cronJob.enabled) {
        await pauseCronJob(cronJob.cron_job_id);
        toast.success('Cron job paused successfully!');
      } else {
        await resumeCronJob(cronJob.cron_job_id);
        toast.success('Cron job resumed successfully!');
      }
      refetch();
    } catch (error) {
      toast.error('Failed to update cron job: ' + (error as Error).message);
    }
  };

  const handleExecuteNow = async (cronJob: CronJob) => {
    try {
      const result = await executeCronJobNow(cronJob.cron_job_id);
      if (result.success) {
        toast.success('Cron job executed successfully!');
      } else {
        toast.error('Cron job execution failed: ' + result.message);
      }
      refetch();
    } catch (error) {
      toast.error('Failed to execute cron job: ' + (error as Error).message);
    }
  };

  const columns: ColumnDef<CronJob>[] = [
    {
      accessorKey: 'cron_job_id',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Cron Job ID
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => <div className="font-medium">{row.getValue('cron_job_id')}</div>,
    },
    {
      accessorKey: 'schedule',
      header: 'Schedule',
      cell: ({ row }) => (
        <div className="font-mono text-sm">{row.getValue('schedule')}</div>
      ),
    },
    {
      accessorKey: 'target_session_id',
      header: 'Target Session',
      cell: ({ row }) => (
        <div className="font-mono text-sm">{row.getValue('target_session_id')}</div>
      ),
    },
    {
      accessorKey: 'enabled',
      header: 'Enabled',
      cell: ({ row }) => {
        const enabled = row.getValue('enabled') as boolean;
        return (
          <Badge variant={enabled ? 'default' : 'outline'}>
            {enabled ? 'Yes' : 'No'}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'next_execution_at',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Next Execution
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => {
        const date = row.getValue('next_execution_at') as string | undefined;
        return <div>{date ? new Date(date).toLocaleString() : 'N/A'}</div>;
      },
    },
    {
      accessorKey: 'last_executed_at',
      header: 'Last Executed',
      cell: ({ row }) => {
        const date = row.getValue('last_executed_at') as string | undefined;
        return <div>{date ? new Date(date).toLocaleString() : 'Never'}</div>;
      },
    },
    {
      id: 'actions',
      enableHiding: false,
      cell: ({ row }) => {
        const cronJob = row.original;

        const handleEdit = () => {
          setSelectedCronJob(cronJob);
          setDialogOpen(true);
        };

        const handleViewHistory = () => {
          setSelectedCronJob(cronJob);
          setHistoryDrawerOpen(true);
        };

        const handleDelete = async () => {
          if (!confirm(`Delete cron job "${cronJob.cron_job_id}"?`)) {
            return;
          }

          try {
            await deleteCronJob(cronJob.cron_job_id);
            toast.success('Cron job deleted successfully!');
            refetch();
          } catch (error) {
            toast.error('Failed to delete cron job: ' + (error as Error).message);
          }
        };

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Actions</DropdownMenuLabel>
              <DropdownMenuItem
                onClick={() => navigator.clipboard.writeText(cronJob.cron_job_id)}
              >
                Copy cron job ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => handlePauseResume(cronJob)}>
                {cronJob.enabled ? (
                  <>
                    <Pause className="mr-2 h-4 w-4" />
                    Pause
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Resume
                  </>
                )}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExecuteNow(cronJob)}>
                <Play className="mr-2 h-4 w-4" />
                Execute now
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleViewHistory}>
                <History className="mr-2 h-4 w-4" />
                View history
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleEdit}>
                Edit cron job
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive" onClick={handleDelete}>
                Delete cron job
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];

  const table = useReactTable({
    data: cronJobs || [],
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
    },
  });

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error Loading Cron Jobs</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>Unable to fetch cron job data from the backend.</p>
          <p className="text-sm">Error: {error}</p>
          <p className="text-sm mt-2">Required endpoint: <code className="bg-muted px-1 py-0.5 rounded">/api/gateway/cron-jobs</code></p>
          <Button onClick={refetch} className="mt-4" size="sm">
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const handleAddCronJob = () => {
    setSelectedCronJob(null);
    setDialogOpen(true);
  };

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Input
            placeholder="Search by cron job ID..."
            value={(table.getColumn('cron_job_id')?.getFilterValue() as string) ?? ''}
            onChange={(event) =>
              table.getColumn('cron_job_id')?.setFilterValue(event.target.value)
            }
            className="max-w-sm"
          />
          <div className="flex items-center space-x-2">
            <Switch
              id="enabled-filter"
              checked={enabledFilter === true}
              onCheckedChange={(checked) => setEnabledFilter(checked ? true : undefined)}
            />
            <Label htmlFor="enabled-filter">Show enabled only</Label>
          </div>
        </div>
        <Button onClick={handleAddCronJob}>
          <Plus className="mr-2 h-4 w-4" />
          Create Cron Job
        </Button>
      </div>

      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  Loading cron jobs...
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() && 'selected'}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <Clock className="h-8 w-8 text-muted-foreground" />
                    <p className="text-muted-foreground">No cron jobs found.</p>
                    <Button variant="outline" size="sm" onClick={handleAddCronJob}>
                      <Plus className="mr-2 h-4 w-4" />
                      Create your first cron job
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end space-x-2 py-4">
        <div className="text-muted-foreground flex-1 text-sm">
          {table.getFilteredRowModel().rows.length} cron job(s) total
        </div>
        <div className="space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>

      <CronJobDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        cronJob={selectedCronJob}
        onSuccess={() => {
          refetch();
        }}
      />

      <CronExecutionHistoryDrawer
        open={historyDrawerOpen}
        onOpenChange={setHistoryDrawerOpen}
        cronJobId={selectedCronJob?.cron_job_id || null}
      />
    </div>
  );
}
