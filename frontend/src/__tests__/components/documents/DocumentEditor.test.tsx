import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DocumentEditor } from '@/components/documents/DocumentEditor';

// Mock MarkdownRenderer
vi.mock('@/components/documents/MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => <div data-testid="preview">{content}</div>,
}));

describe('DocumentEditor', () => {
  const mockDoc = {
    path: 'test/doc.md',
    content: '# Test\n\nOriginal content.',
    metadata: {
      size: 30,
      modified: '2026-02-20T10:00:00Z',
      word_count: 3,
    },
  };

  const onSave = vi.fn().mockResolvedValue(undefined);
  const onCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders textarea with document content', () => {
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    expect(textarea).toHaveValue('# Test\n\nOriginal content.');
  });

  it('save button is disabled when no changes', () => {
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    expect(screen.getByText('Save').closest('button')).toBeDisabled();
  });

  it('shows "Unsaved changes" badge after editing', async () => {
    const user = userEvent.setup();
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    await user.type(textarea, ' extra');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });

  it('save button calls onSave with content', async () => {
    const user = userEvent.setup();
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    await user.type(textarea, ' more');
    await user.click(screen.getByText('Save'));
    expect(onSave).toHaveBeenCalledWith('# Test\n\nOriginal content. more');
  });

  it('cancel without changes calls onCancel directly', async () => {
    const user = userEvent.setup();
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    await user.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalled();
  });

  it('cancel with changes triggers confirm dialog', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    await user.type(textarea, ' changed');
    await user.click(screen.getByText('Cancel'));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('shows word count, line count, character count in footer stats', () => {
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    // "# Test\n\nOriginal content." → 4 words, 3 lines, 25 chars
    expect(screen.getByText('4 words')).toBeInTheDocument();
    expect(screen.getByText('3 lines')).toBeInTheDocument();
    expect(screen.getByText('25 characters')).toBeInTheDocument();
  });

  it('Ctrl+S triggers save when dirty', async () => {
    const user = userEvent.setup();
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    await user.type(textarea, ' extra');
    fireEvent.keyDown(textarea, { key: 's', ctrlKey: true });
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
  });

  it('Ctrl+S does nothing when not dirty', () => {
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    fireEvent.keyDown(textarea, { key: 's', ctrlKey: true });
    expect(onSave).not.toHaveBeenCalled();
  });

  it('localStorage recovery: stores content on dirty change', async () => {
    const user = userEvent.setup();
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    await user.type(textarea, ' saved');
    await waitFor(() => {
      expect(localStorage.getItem('document-recovery-test/doc.md')).toBe('# Test\n\nOriginal content. saved');
    });
  });

  it('localStorage recovery: prompts to restore on mount if recovery data exists', () => {
    localStorage.setItem('document-recovery-test/doc.md', '# Recovered');
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    expect(confirmSpy).toHaveBeenCalledWith(
      'Found unsaved changes from a previous session. Would you like to recover them?'
    );
    expect(screen.getByRole('textbox')).toHaveValue('# Recovered');
    confirmSpy.mockRestore();
  });

  it('unsaved changes badge has role="status"', async () => {
    const user = userEvent.setup();
    render(<DocumentEditor document={mockDoc} onSave={onSave} onCancel={onCancel} />);
    const textarea = screen.getByRole('textbox');
    await user.type(textarea, ' x');
    const badge = screen.getByText('Unsaved changes');
    expect(badge).toHaveAttribute('role', 'status');
  });
});
