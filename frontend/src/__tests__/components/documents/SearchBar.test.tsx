import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SearchBar } from '@/components/documents/SearchBar';

describe('SearchBar', () => {
  const onSearch = vi.fn();
  const onChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders search input', () => {
    render(<SearchBar value="" onChange={onChange} onSearch={onSearch} />);
    expect(screen.getByPlaceholderText('Search documents...')).toBeInTheDocument();
  });

  it('calls onChange when typing', async () => {
    const user = userEvent.setup();
    render(<SearchBar value="" onChange={onChange} onSearch={onSearch} />);
    const input = screen.getByPlaceholderText('Search documents...');
    await user.type(input, 'a');
    expect(onChange).toHaveBeenCalledWith('a');
  });

  it('shows clear button when value is present', () => {
    render(<SearchBar value="test" onChange={onChange} onSearch={onSearch} />);
    expect(screen.getByLabelText('Clear search')).toBeInTheDocument();
  });

  it('hides clear button when value is empty', () => {
    render(<SearchBar value="" onChange={onChange} onSearch={onSearch} />);
    expect(screen.queryByLabelText('Clear search')).not.toBeInTheDocument();
  });

  it('calls onChange with empty string when clear is clicked', async () => {
    const user = userEvent.setup();
    render(<SearchBar value="test" onChange={onChange} onSearch={onSearch} />);
    await user.click(screen.getByLabelText('Clear search'));
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('clears input on Escape key', async () => {
    const user = userEvent.setup();
    render(<SearchBar value="test" onChange={onChange} onSearch={onSearch} />);
    const input = screen.getByPlaceholderText('Search documents...');
    await user.click(input);
    await user.keyboard('{Escape}');
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('debounces onSearch calls', async () => {
    vi.useFakeTimers();
    const onSearchDebounced = vi.fn();
    const { rerender } = render(<SearchBar value="" onChange={onChange} onSearch={onSearchDebounced} debounceMs={300} />);
    // Simulate rapid typing by rerendering with different values
    rerender(<SearchBar value="a" onChange={onChange} onSearch={onSearchDebounced} debounceMs={300} />);
    rerender(<SearchBar value="ab" onChange={onChange} onSearch={onSearchDebounced} debounceMs={300} />);
    rerender(<SearchBar value="abc" onChange={onChange} onSearch={onSearchDebounced} debounceMs={300} />);
    // Before debounce timeout, only the initial useEffect from first render may fire
    vi.advanceTimersByTime(300);
    // After debounce, the final value should trigger onSearch
    expect(onSearchDebounced).toHaveBeenCalledWith('abc');
    vi.useRealTimers();
  });

  it('Ctrl+F focuses the search input', () => {
    render(<SearchBar value="" onChange={onChange} onSearch={onSearch} />);
    const input = screen.getByPlaceholderText('Search documents...');
    fireEvent.keyDown(window, { key: 'f', ctrlKey: true });
    expect(document.activeElement).toBe(input);
  });

  it('has role="search" wrapper', () => {
    render(<SearchBar value="" onChange={onChange} onSearch={onSearch} />);
    expect(screen.getByRole('search')).toBeInTheDocument();
  });
});
