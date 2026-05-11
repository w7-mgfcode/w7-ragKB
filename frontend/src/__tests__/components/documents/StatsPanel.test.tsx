import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatsPanel } from '@/components/documents/StatsPanel';

describe('StatsPanel', () => {
  const mockStats = {
    total_directories: 5,
    total_documents: 1234,
    total_subdirectories: 12,
    total_words: 56789,
  };

  it('renders loading skeletons when loading', () => {
    const { container } = render(<StatsPanel stats={mockStats} loading={true} />);
    // Skeletons are rendered instead of numbers
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0);
  });

  it('renders all 4 stat cards with correct labels', () => {
    render(<StatsPanel stats={mockStats} loading={false} />);
    expect(screen.getByText('Spaces/Categories')).toBeInTheDocument();
    expect(screen.getByText('Pages/Documents')).toBeInTheDocument();
    expect(screen.getByText('Sections')).toBeInTheDocument();
    expect(screen.getByText('Words')).toBeInTheDocument();
  });

  it('renders formatted numbers', () => {
    render(<StatsPanel stats={mockStats} loading={false} />);
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('1,234')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('56,789')).toBeInTheDocument();
  });

  it('displays zero values correctly', () => {
    const zeroStats = {
      total_directories: 0,
      total_documents: 0,
      total_subdirectories: 0,
      total_words: 0,
    };
    render(<StatsPanel stats={zeroStats} loading={false} />);
    const zeros = screen.getAllByText('0');
    expect(zeros).toHaveLength(4);
  });

  it('renders null when stats is undefined and not loading', () => {
    const { container } = render(<StatsPanel stats={undefined} loading={false} />);
    expect(container.innerHTML).toBe('');
  });

  it('has aria-label on stat cards', () => {
    render(<StatsPanel stats={mockStats} loading={false} />);
    expect(screen.getByLabelText('Spaces/Categories: 5')).toBeInTheDocument();
    expect(screen.getByLabelText('Pages/Documents: 1,234')).toBeInTheDocument();
  });
});
