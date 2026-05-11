import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BulkActionsToolbar } from '@/components/documents/BulkActionsToolbar';
import { toast } from 'sonner';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe('BulkActionsToolbar', () => {
  const onBulkDelete = vi.fn().mockResolvedValue({ successful: ['a.md', 'b.md'], failed: [] });
  const onBulkMove = vi.fn().mockResolvedValue({ successful: ['a.md', 'b.md'], failed: [] });
  const onClearSelection = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when no selection', () => {
    const { container } = render(
      <BulkActionsToolbar
        selectedPaths={[]}
        onBulkDelete={onBulkDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={['security', 'operations']}
      />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders toolbar when paths are selected', () => {
    render(
      <BulkActionsToolbar
        selectedPaths={['a.md', 'b.md']}
        onBulkDelete={onBulkDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={['security']}
      />
    );
    expect(screen.getByText('2 selected')).toBeInTheDocument();
    expect(screen.getByText('Delete')).toBeInTheDocument();
    expect(screen.getByText('Move')).toBeInTheDocument();
    expect(screen.getByText('Clear')).toBeInTheDocument();
  });

  it('delete button opens confirmation dialog', async () => {
    const user = userEvent.setup();
    render(
      <BulkActionsToolbar
        selectedPaths={['a.md']}
        onBulkDelete={onBulkDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={[]}
      />
    );
    await user.click(screen.getByText('Delete'));
    expect(screen.getByText('Delete 1 documents?')).toBeInTheDocument();
  });

  it('clear selection button calls onClearSelection', async () => {
    const user = userEvent.setup();
    render(
      <BulkActionsToolbar
        selectedPaths={['a.md']}
        onBulkDelete={onBulkDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={[]}
      />
    );
    await user.click(screen.getByText('Clear'));
    expect(onClearSelection).toHaveBeenCalled();
  });

  it('move button opens move dialog with directory selector', async () => {
    const user = userEvent.setup();
    render(
      <BulkActionsToolbar
        selectedPaths={['a.md']}
        onBulkDelete={onBulkDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={['security', 'operations']}
      />
    );
    await user.click(screen.getByText('Move'));
    expect(screen.getByText('Move 1 documents')).toBeInTheDocument();
    expect(screen.getByText('Select target directory')).toBeInTheDocument();
  });

  it('delete confirmation executes onBulkDelete and shows toast', async () => {
    const user = userEvent.setup();
    render(
      <BulkActionsToolbar
        selectedPaths={['a.md']}
        onBulkDelete={onBulkDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={[]}
      />
    );
    await user.click(screen.getByText('Delete'));
    // Click the delete confirm button in the dialog
    const deleteBtn = screen.getAllByText('Delete').find(
      (el) => el.closest('[role="alertdialog"]')
    );
    if (deleteBtn) {
      await user.click(deleteBtn);
    }
    await waitFor(() => {
      expect(onBulkDelete).toHaveBeenCalled();
    });
  });

  it('shows error toast when bulk delete fails', async () => {
    const failingDelete = vi.fn().mockRejectedValue(new Error('Network error'));
    const user = userEvent.setup();
    render(
      <BulkActionsToolbar
        selectedPaths={['a.md']}
        onBulkDelete={failingDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={[]}
      />
    );
    await user.click(screen.getByText('Delete'));
    const deleteBtn = screen.getAllByText('Delete').find(
      (el) => el.closest('[role="alertdialog"]')
    );
    if (deleteBtn) {
      await user.click(deleteBtn);
    }
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
  });

  it('toolbar has role="toolbar" and aria-label', () => {
    render(
      <BulkActionsToolbar
        selectedPaths={['a.md']}
        onBulkDelete={onBulkDelete}
        onBulkMove={onBulkMove}
        onClearSelection={onClearSelection}
        directories={[]}
      />
    );
    expect(screen.getByRole('toolbar')).toHaveAttribute('aria-label', 'Bulk actions');
  });
});
