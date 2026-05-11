import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DocumentTree } from '@/components/documents/DocumentTree';
import type { TreeNode } from '@/types/documents';

// Mock the announcer to avoid DOM side effects
vi.mock('@/lib/announcer', () => ({
  announce: vi.fn(),
}));

const mockTree: TreeNode[] = [
  {
    type: 'directory',
    name: 'security',
    path: 'security',
    children: [
      {
        type: 'document',
        name: 'auth.md',
        path: 'security/auth.md',
        metadata: { size: 1024, modified: '2026-01-01T00:00:00Z', word_count: 150 },
      },
      {
        type: 'document',
        name: 'rbac.md',
        path: 'security/rbac.md',
        metadata: { size: 2048, modified: '2026-01-02T00:00:00Z', word_count: 300 },
      },
    ],
  },
  {
    type: 'directory',
    name: 'operations',
    path: 'operations',
    children: [
      {
        type: 'document',
        name: 'deploy.md',
        path: 'operations/deploy.md',
        metadata: { size: 512, modified: '2026-01-04T00:00:00Z', word_count: 80 },
      },
    ],
  },
  {
    type: 'document',
    name: 'readme.md',
    path: 'readme.md',
    metadata: { size: 512, modified: '2026-01-03T00:00:00Z', word_count: 50 },
  },
];

describe('DocumentTree', () => {
  const onSelect = vi.fn();
  const onToggleSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state message when nodes=[]', () => {
    render(
      <DocumentTree
        nodes={[]}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    expect(screen.getByText('No documents found')).toBeInTheDocument();
  });

  it('renders search empty state when searchQuery has no matches', () => {
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery="nonexistent"
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    expect(screen.getByText('No documents match your search')).toBeInTheDocument();
  });

  it('renders directory nodes with folder name', () => {
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    expect(screen.getByText('security')).toBeInTheDocument();
    expect(screen.getByText('operations')).toBeInTheDocument();
  });

  it('renders document nodes with name and word count badge', () => {
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    expect(screen.getByText('readme.md')).toBeInTheDocument();
    expect(screen.getByText('50w')).toBeInTheDocument();
  });

  it('expands directory on click — shows children', async () => {
    const user = userEvent.setup();
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    expect(screen.queryByText('auth.md')).not.toBeInTheDocument();
    await user.click(screen.getByText('security'));
    expect(screen.getByText('auth.md')).toBeInTheDocument();
    expect(screen.getByText('rbac.md')).toBeInTheDocument();
  });

  it('collapses expanded directory on click — hides children', async () => {
    const user = userEvent.setup();
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    await user.click(screen.getByText('security'));
    expect(screen.getByText('auth.md')).toBeInTheDocument();
    await user.click(screen.getByText('security'));
    expect(screen.queryByText('auth.md')).not.toBeInTheDocument();
  });

  it('highlights selected document with bg-accent class', () => {
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath="readme.md"
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    const node = screen.getByText('readme.md').closest('[role="treeitem"]');
    expect(node?.className).toContain('bg-accent');
  });

  it('calls onSelect when document node clicked', async () => {
    const user = userEvent.setup();
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    await user.click(screen.getByText('readme.md'));
    expect(onSelect).toHaveBeenCalledWith('readme.md');
  });

  it('calls onToggleSelect when checkbox clicked (does NOT call onSelect)', async () => {
    const user = userEvent.setup();
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    // The checkbox is inside the readme.md treeitem
    const treeItem = screen.getByText('readme.md').closest('[role="treeitem"]')!;
    const checkbox = within(treeItem).getByRole('checkbox');
    await user.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledWith('readme.md');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('search filtering: shows ancestor directory and hides non-matching nodes', () => {
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery="auth"
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    // auth.md matches, its parent 'security' should be shown
    expect(screen.getByText('security')).toBeInTheDocument();
    // Non-matching root-level nodes hidden
    expect(screen.queryByText('readme.md')).not.toBeInTheDocument();
    expect(screen.queryByText('operations')).not.toBeInTheDocument();
  });

  it('search filtering: highlights matching text with yellow background', () => {
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery="readme"
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    // readme.md is a top-level document node, should have highlighted text
    const highlight = document.querySelector('.bg-yellow-200');
    expect(highlight).toBeInTheDocument();
    expect(highlight?.textContent).toBe('readme');
  });

  it('renders tree with correct ARIA roles', () => {
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    expect(screen.getByRole('tree')).toBeInTheDocument();
    const treeItems = screen.getAllByRole('treeitem');
    expect(treeItems.length).toBeGreaterThanOrEqual(3); // 2 dirs + 1 doc
  });

  it('directory nodes have aria-expanded attribute', async () => {
    const user = userEvent.setup();
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    const securityItem = screen.getByText('security').closest('[role="treeitem"]');
    expect(securityItem).toHaveAttribute('aria-expanded', 'false');
    await user.click(screen.getByText('security'));
    expect(securityItem).toHaveAttribute('aria-expanded', 'true');
  });

  it('renders nested tree at correct indentation depths', async () => {
    const user = userEvent.setup();
    render(
      <DocumentTree
        nodes={mockTree}
        selectedPath={null}
        onSelect={onSelect}
        searchQuery=""
        selectedPaths={new Set()}
        onToggleSelect={onToggleSelect}
      />
    );
    // Top-level directory: depth 0 → paddingLeft = 0*16+8 = 8px
    const securityNode = screen.getByText('security').closest('[role="treeitem"]');
    expect(securityNode?.style.paddingLeft).toBe('8px');

    // Expand and check child depth
    await user.click(screen.getByText('security'));
    const authNode = screen.getByText('auth.md').closest('[role="treeitem"]');
    // Child document: depth 1 → paddingLeft = 1*16+32 = 48px
    expect(authNode?.style.paddingLeft).toBe('48px');
  });
});
