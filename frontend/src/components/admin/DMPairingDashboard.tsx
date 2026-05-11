/**
 * DM Pairing Dashboard Component
 * 
 * Manages user approval for direct message access with DM pairing security.
 * Features:
 * - Tab 1: Pending Approvals - users awaiting approval with approval codes
 * - Tab 2: Approved Users - approved users with approval timestamp
 * - Tab 3: Approval History - log of all approval/rejection events
 * - Generate approval codes
 * - Approve/revoke user access
 * - Search by user ID
 * - Approval code expiration countdown
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
} from '@tanstack/react-table';
import { ArrowUpDown, Clock, CheckCircle, XCircle, Plus, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useChannelUsers, useApprovalHistory } from '@/hooks/useDMPairing';
import { approveUser, revokeApproval, generateApprovalCode } from '@/lib/api';
import type { ChannelUser, ApprovalEvent } from '@/types/gateway';
import { toast } from 'sonner';
import { GenerateCodeDialog } from './GenerateCodeDialog';

export function DMPairingDashboard() {
  const [searchQuery, setSearchQuery] = React.useState('');
  const [activeTab, setActiveTab] = React.useState('pending');
  const [generateDialogOpen, setGenerateDialogOpen] = React.useState(false);
  const [revokeDialogOpen, setRevokeDialogOpen] = React.useState(false);
  const [userToRevoke, setUserToRevoke] = React.useState<ChannelUser | null>(null);
  const [isProcessing, setIsProcessing] = React.useState(false);

  // Fetch pending users
  const { users: pendingUsers, loading: pendingLoading, error: pendingError, refetch: refetchPending } = useChannelUsers({
    approved: false,
    search: searchQuery,
  });

  // Fetch approved users
  const { users: approvedUsers, loading: approvedLoading, error: approvedError, refetch: refetchApproved } = useChannelUsers({
    approved: true,
    search: searchQuery,
  });

  // Fetch approval history
  const { history, loading: historyLoading, error: historyError, refetch: refetchHistory } = useApprovalHistory();

  // Calculate time remaining for approval code expiration
  const getTimeRemaining = (expiresAt?: string): string => {
    if (!expiresAt) return 'N/A';
    
    const now = new Date();
    const expiry = new Date(expiresAt);
    const diff = expiry.getTime() - now.getTime();
    
    if (diff <= 0) return 'Expired';
    
    const minutes = Math.floor(diff / 60000);
    const seconds = Math.floor((diff % 60000) / 1000);
    
    return `${minutes}m ${seconds}s`;
  };

  // Auto-refresh countdown every second
  React.useEffect(() => {
    const interval = setInterval(() => {
      // Force re-render to update countdown
      if (activeTab === 'pending' && pendingUsers.length > 0) {
        refetchPending();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [activeTab, pendingUsers.length, refetchPending]);

  // Pending approvals columns
  const pendingColumns: ColumnDef<ChannelUser>[] = [
    {
      accessorKey: 'user_id',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            User ID
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => <div className="font-medium">{row.getValue('user_id')}</div>,
    },
    {
      accessorKey: 'user_name',
      header: 'User Name',
      cell: ({ row }) => <div>{row.getValue('user_name') || 'N/A'}</div>,
    },
    {
      accessorKey: 'channel_id',
      header: 'Channel',
      cell: ({ row }) => <div className="font-mono text-sm">{row.getValue('channel_id')}</div>,
    },
    {
      accessorKey: 'approval_code',
      header: 'Approval Code',
      cell: ({ row }) => {
        const code = row.getValue('approval_code') as string | undefined;
        return (
          <div className="flex items-center gap-2">
            <code className="px-2 py-1 bg-muted rounded text-sm font-mono">
              {code || 'N/A'}
            </code>
            {code && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(code);
                  toast.success('Code copied to clipboard');
                }}
              >
                Copy
              </Button>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: 'approval_code_expires_at',
      header: 'Expires In',
      cell: ({ row }) => {
        const expiresAt = row.getValue('approval_code_expires_at') as string | undefined;
        const timeRemaining = getTimeRemaining(expiresAt);
        const isExpired = timeRemaining === 'Expired';
        
        return (
          <div className="flex items-center gap-2">
            <Clock className={`h-4 w-4 ${isExpired ? 'text-destructive' : 'text-muted-foreground'}`} />
            <span className={isExpired ? 'text-destructive' : ''}>{timeRemaining}</span>
          </div>
        );
      },
    },
    {
      id: 'actions',
      cell: ({ row }) => {
        const user = row.original;
        
        const handleApprove = async () => {
          setIsProcessing(true);
          try {
            await approveUser({ channel_user_id: user.channel_user_id });
            toast.success('User approved successfully!');
            refetchPending();
            refetchApproved();
            refetchHistory();
          } catch (error) {
            toast.error('Failed to approve user: ' + (error as Error).message);
          } finally {
            setIsProcessing(false);
          }
        };

        return (
          <Button
            variant="default"
            size="sm"
            onClick={handleApprove}
            disabled={isProcessing}
          >
            <CheckCircle className="mr-2 h-4 w-4" />
            Approve
          </Button>
        );
      },
    },
  ];

  // Approved users columns
  const approvedColumns: ColumnDef<ChannelUser>[] = [
    {
      accessorKey: 'user_id',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            User ID
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => <div className="font-medium">{row.getValue('user_id')}</div>,
    },
    {
      accessorKey: 'user_name',
      header: 'User Name',
      cell: ({ row }) => <div>{row.getValue('user_name') || 'N/A'}</div>,
    },
    {
      accessorKey: 'channel_id',
      header: 'Channel',
      cell: ({ row }) => <div className="font-mono text-sm">{row.getValue('channel_id')}</div>,
    },
    {
      accessorKey: 'approved_at',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Approved At
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => {
        const date = row.getValue('approved_at') as string | undefined;
        return <div>{date ? new Date(date).toLocaleString() : 'N/A'}</div>;
      },
    },
    {
      id: 'actions',
      cell: ({ row }) => {
        const user = row.original;
        
        const handleRevoke = () => {
          setUserToRevoke(user);
          setRevokeDialogOpen(true);
        };

        return (
          <Button
            variant="destructive"
            size="sm"
            onClick={handleRevoke}
            disabled={isProcessing}
          >
            <XCircle className="mr-2 h-4 w-4" />
            Revoke
          </Button>
        );
      },
    },
  ];

  // Approval history columns
  const historyColumns: ColumnDef<ApprovalEvent>[] = [
    {
      accessorKey: 'timestamp',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Timestamp
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => {
        const date = new Date(row.getValue('timestamp'));
        return <div>{date.toLocaleString()}</div>;
      },
    },
    {
      accessorKey: 'event_type',
      header: 'Event',
      cell: ({ row }) => {
        const type = row.getValue('event_type') as string;
        const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
          generated: 'secondary',
          approved: 'default',
          rejected: 'destructive',
          revoked: 'outline',
        };
        return (
          <Badge variant={variants[type] || 'outline'} className="capitalize">
            {type}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'user_id',
      header: 'User ID',
      cell: ({ row }) => <div className="font-medium">{row.getValue('user_id')}</div>,
    },
    {
      accessorKey: 'user_name',
      header: 'User Name',
      cell: ({ row }) => <div>{row.getValue('user_name') || 'N/A'}</div>,
    },
    {
      accessorKey: 'channel_id',
      header: 'Channel',
      cell: ({ row }) => <div className="font-mono text-sm">{row.getValue('channel_id')}</div>,
    },
    {
      accessorKey: 'details',
      header: 'Details',
      cell: ({ row }) => <div className="text-sm text-muted-foreground">{row.getValue('details') || '-'}</div>,
    },
  ];

  const handleConfirmRevoke = async () => {
    if (!userToRevoke) return;
    
    setIsProcessing(true);
    try {
      await revokeApproval(userToRevoke.channel_user_id);
      toast.success('User approval revoked successfully!');
      refetchPending();
      refetchApproved();
      refetchHistory();
    } catch (error) {
      toast.error('Failed to revoke approval: ' + (error as Error).message);
    } finally {
      setIsProcessing(false);
      setRevokeDialogOpen(false);
      setUserToRevoke(null);
    }
  };

  const handleGenerateCode = () => {
    setGenerateDialogOpen(true);
  };

  const handleCodeGenerated = () => {
    refetchPending();
    refetchHistory();
  };

  return (
    <div className="w-full space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5" />
                DM Pairing Management
              </CardTitle>
              <CardDescription>
                Manage user approval for direct message access
              </CardDescription>
            </div>
            <Button onClick={handleGenerateCode}>
              <Plus className="mr-2 h-4 w-4" />
              Generate Code
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Input
              placeholder="Search by user ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="max-w-sm"
            />

            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="pending">
                  Pending Approvals
                  {pendingUsers.length > 0 && (
                    <Badge variant="secondary" className="ml-2">
                      {pendingUsers.length}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="approved">
                  Approved Users
                  {approvedUsers.length > 0 && (
                    <Badge variant="default" className="ml-2">
                      {approvedUsers.length}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="history">Approval History</TabsTrigger>
              </TabsList>

              <TabsContent value="pending" className="space-y-4">
                {pendingError && (
                  <Alert variant="destructive">
                    <AlertDescription>Error loading pending approvals: {pendingError}</AlertDescription>
                  </Alert>
                )}
                
                <PendingApprovalsTable
                  data={pendingUsers}
                  columns={pendingColumns}
                  loading={pendingLoading}
                />
              </TabsContent>

              <TabsContent value="approved" className="space-y-4">
                {approvedError && (
                  <Alert variant="destructive">
                    <AlertDescription>Error loading approved users: {approvedError}</AlertDescription>
                  </Alert>
                )}
                
                <ApprovedUsersTable
                  data={approvedUsers}
                  columns={approvedColumns}
                  loading={approvedLoading}
                />
              </TabsContent>

              <TabsContent value="history" className="space-y-4">
                {historyError && (
                  <Alert variant="destructive">
                    <AlertDescription>Error loading approval history: {historyError}</AlertDescription>
                  </Alert>
                )}
                
                <ApprovalHistoryTable
                  data={history}
                  columns={historyColumns}
                  loading={historyLoading}
                />
              </TabsContent>
            </Tabs>
          </div>
        </CardContent>
      </Card>

      <GenerateCodeDialog
        open={generateDialogOpen}
        onOpenChange={setGenerateDialogOpen}
        onSuccess={handleCodeGenerated}
      />

      <AlertDialog open={revokeDialogOpen} onOpenChange={setRevokeDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke User Approval</AlertDialogTitle>
            <AlertDialogDescription>
              This will revoke the user's approval and they will no longer be able to send direct messages.
              {userToRevoke && (
                <div className="mt-4 p-3 bg-muted rounded-md">
                  <p className="font-medium">User: {userToRevoke.user_id}</p>
                  <p className="text-sm">Channel: {userToRevoke.channel_id}</p>
                </div>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isProcessing}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmRevoke}
              disabled={isProcessing}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isProcessing ? 'Revoking...' : 'Revoke Approval'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// Table components for each tab
function PendingApprovalsTable({ data, columns, loading }: { data: ChannelUser[]; columns: ColumnDef<ChannelUser>[]; loading: boolean }) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);

  const table = useReactTable({
    data,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: {
      sorting,
      columnFilters,
    },
  });

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  Loading pending approvals...
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
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
                    <Shield className="h-8 w-8 text-muted-foreground" />
                    <p className="text-muted-foreground">No pending approvals.</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end space-x-2">
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
  );
}

function ApprovedUsersTable({ data, columns, loading }: { data: ChannelUser[]; columns: ColumnDef<ChannelUser>[]; loading: boolean }) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);

  const table = useReactTable({
    data,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: {
      sorting,
      columnFilters,
    },
  });

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  Loading approved users...
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
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
                    <CheckCircle className="h-8 w-8 text-muted-foreground" />
                    <p className="text-muted-foreground">No approved users.</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end space-x-2">
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
  );
}

function ApprovalHistoryTable({ data, columns, loading }: { data: ApprovalEvent[]; columns: ColumnDef<ApprovalEvent>[]; loading: boolean }) {
  const [sorting, setSorting] = React.useState<SortingState>([{ id: 'timestamp', desc: true }]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);

  const table = useReactTable({
    data,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    state: {
      sorting,
      columnFilters,
    },
  });

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  Loading approval history...
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
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
                    <p className="text-muted-foreground">No approval history.</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end space-x-2">
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
  );
}
