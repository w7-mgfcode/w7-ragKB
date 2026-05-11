import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SyncStatusBadge } from '@/components/documents/SyncStatusBadge';
import type { SyncStatus } from '@/types/documents';

describe('SyncStatusBadge', () => {
  const allStatuses: Array<{ status: SyncStatus; label: string }> = [
    { status: 'in_sync', label: 'In Sync' },
    { status: 'out_of_sync', label: 'Out of Sync' },
    { status: 'processing', label: 'Processing' },
    { status: 'error', label: 'Error' },
    { status: 'orphaned_chunks', label: 'Orphaned' },
    { status: 'pending_indexing', label: 'Pending' },
  ];

  it.each(allStatuses)(
    'renders correct aria-label for $status',
    ({ status, label }) => {
      render(<SyncStatusBadge status={status} />);
      const badge = screen.getByRole('status');
      expect(badge).toBeInTheDocument();
      expect(badge.getAttribute('aria-label')).toContain(label);
    },
  );

  it('shows error message in aria-label when error status', () => {
    render(
      <SyncStatusBadge status="error" errorMessage="Embedding failed" />,
    );
    const badge = screen.getByRole('status');
    expect(badge.getAttribute('aria-label')).toContain('Embedding failed');
  });

  it('renders text label in md size', () => {
    render(<SyncStatusBadge status="in_sync" size="md" />);
    expect(screen.getByText('In Sync')).toBeInTheDocument();
  });

  it('does not render text label in sm size', () => {
    render(<SyncStatusBadge status="in_sync" size="sm" />);
    expect(screen.queryByText('In Sync')).not.toBeInTheDocument();
  });

  it('renders animate-spin class for processing status', () => {
    const { container } = render(<SyncStatusBadge status="processing" />);
    const spinIcon = container.querySelector('.animate-spin');
    expect(spinIcon).toBeTruthy();
  });

  it('does not render animate-spin for non-processing status', () => {
    const { container } = render(<SyncStatusBadge status="in_sync" />);
    const spinIcon = container.querySelector('.animate-spin');
    expect(spinIcon).toBeNull();
  });
});
