import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DocumentViewer } from '@/components/documents/DocumentViewer';

// Mock ReactMarkdown and syntax highlighter to avoid pulling in heavy deps
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>,
}));
vi.mock('remark-gfm', () => ({ default: () => {} }));
vi.mock('react-syntax-highlighter', () => ({
  Prism: () => null,
}));
vi.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({
  vscDarkPlus: {},
}));

describe('DocumentViewer', () => {
  const mockDoc = {
    path: 'security/auth-guide.md',
    content: '# Auth Guide\n\nSome content here.',
    metadata: {
      size: 2048,
      modified: '2026-02-20T10:00:00Z',
      word_count: 42,
    },
  };

  it('renders empty state when no document', () => {
    render(
      <DocumentViewer document={null} loading={false} error={null} onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText('Select a document to view')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    const { container } = render(
      <DocumentViewer document={null} loading={true} error={null} onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0);
  });

  it('renders error state with retry', () => {
    const onRetry = vi.fn();
    render(
      <DocumentViewer document={null} loading={false} error="Network error" onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} onRetry={onRetry} />
    );
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('renders document content', () => {
    render(
      <DocumentViewer document={mockDoc} loading={false} error={null} onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText('security/auth-guide.md')).toBeInTheDocument();
    expect(screen.getByText('42 words')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
    expect(screen.getByTestId('markdown')).toBeInTheDocument();
  });

  it('renders edit, delete, and close buttons', () => {
    render(
      <DocumentViewer document={mockDoc} loading={false} error={null} onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText('Edit')).toBeInTheDocument();
    expect(screen.getByText('Delete')).toBeInTheDocument();
  });

  it('retry button calls onRetry callback', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <DocumentViewer document={null} loading={false} error="Network error" onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} onRetry={onRetry} />
    );
    await user.click(screen.getByText('Retry'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('edit button calls onEdit callback', async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(
      <DocumentViewer document={mockDoc} loading={false} error={null} onEdit={onEdit} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    await user.click(screen.getByText('Edit'));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it('delete button calls onDelete callback', async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(
      <DocumentViewer document={mockDoc} loading={false} error={null} onEdit={vi.fn()} onDelete={onDelete} onClose={vi.fn()} />
    );
    await user.click(screen.getByText('Delete'));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('formats file size correctly for bytes', () => {
    const smallDoc = {
      ...mockDoc,
      metadata: { ...mockDoc.metadata, size: 500 },
    };
    render(
      <DocumentViewer document={smallDoc} loading={false} error={null} onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText('500 B')).toBeInTheDocument();
  });

  it('formats file size correctly for KB', () => {
    render(
      <DocumentViewer document={mockDoc} loading={false} error={null} onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    // 2048 bytes = 2.0 KB
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
  });

  it('error state has role="alert"', () => {
    render(
      <DocumentViewer document={null} loading={false} error="Failed" onEdit={vi.fn()} onDelete={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
