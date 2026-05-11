import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CronJobsTable } from '@/components/admin/CronJobsTable';

// Mock child components
vi.mock('@/components/admin/CronJobDialog', () => ({
  CronJobDialog: () => null,
}));
vi.mock('@/components/admin/CronExecutionHistoryDrawer', () => ({
  CronExecutionHistoryDrawer: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/useGateway', () => ({
  useCronJobs: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  deleteCronJob: vi.fn(),
  pauseCronJob: vi.fn(),
  resumeCronJob: vi.fn(),
  executeCronJobNow: vi.fn(),
}));

import { useCronJobs } from '@/hooks/useGateway';

const mockCronJobs = [
  {
    cron_job_id: 'cron-daily-report',
    schedule: '0 9 * * *',
    target_session_id: 'sess-abc-123',
    message_template: 'Generate daily report',
    timezone: 'America/New_York',
    enabled: true,
    created_at: '2024-01-01T00:00:00Z',
    last_executed_at: '2024-01-15T09:00:00Z',
    next_execution_at: '2024-01-16T09:00:00Z',
  },
  {
    cron_job_id: 'cron-weekly-cleanup',
    schedule: '0 0 * * 0',
    target_session_id: 'sess-def-456',
    message_template: 'Run weekly cleanup',
    timezone: 'UTC',
    enabled: false,
    created_at: '2024-02-01T00:00:00Z',
  },
];

describe('CronJobsTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    (useCronJobs as any).mockReturnValue({
      cronJobs: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<CronJobsTable />);
    expect(screen.getByText('Loading cron jobs...')).toBeInTheDocument();
  });

  it('renders cron jobs data in table', () => {
    (useCronJobs as any).mockReturnValue({
      cronJobs: mockCronJobs,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<CronJobsTable />);
    expect(screen.getByText('cron-daily-report')).toBeInTheDocument();
    expect(screen.getByText('cron-weekly-cleanup')).toBeInTheDocument();
    expect(screen.getByText('0 9 * * *')).toBeInTheDocument();
    expect(screen.getByText('0 0 * * 0')).toBeInTheDocument();
    expect(screen.getByText('sess-abc-123')).toBeInTheDocument();
    expect(screen.getByText('sess-def-456')).toBeInTheDocument();
  });

  it('renders empty state with "No cron jobs found."', () => {
    (useCronJobs as any).mockReturnValue({
      cronJobs: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<CronJobsTable />);
    expect(screen.getByText('No cron jobs found.')).toBeInTheDocument();
  });

  it('"Create Cron Job" button exists', () => {
    (useCronJobs as any).mockReturnValue({
      cronJobs: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<CronJobsTable />);
    expect(screen.getByRole('button', { name: /Create Cron Job/i })).toBeInTheDocument();
  });

  it('search input filters cron jobs', async () => {
    const user = userEvent.setup();

    (useCronJobs as any).mockReturnValue({
      cronJobs: mockCronJobs,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<CronJobsTable />);

    const searchInput = screen.getByPlaceholderText('Search by cron job ID...');
    await user.type(searchInput, 'daily');

    await waitFor(() => {
      expect(screen.getByText('cron-daily-report')).toBeInTheDocument();
      expect(screen.queryByText('cron-weekly-cleanup')).not.toBeInTheDocument();
    });
  });

  it('renders error state with retry button', () => {
    const refetchFn = vi.fn();
    (useCronJobs as any).mockReturnValue({
      cronJobs: [],
      loading: false,
      error: 'Failed to fetch cron jobs: 500',
      refetch: refetchFn,
    });

    render(<CronJobsTable />);
    expect(screen.getByText('Error Loading Cron Jobs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });

  it('displays cron job count in footer', () => {
    (useCronJobs as any).mockReturnValue({
      cronJobs: mockCronJobs,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<CronJobsTable />);
    expect(screen.getByText('2 cron job(s) total')).toBeInTheDocument();
  });
});
