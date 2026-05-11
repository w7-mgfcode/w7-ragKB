import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WebhooksTable } from '@/components/admin/WebhooksTable';

// Mock child components
vi.mock('@/components/admin/WebhookDialog', () => ({
  WebhookDialog: () => null,
}));
vi.mock('@/components/admin/TestWebhookDialog', () => ({
  TestWebhookDialog: () => null,
}));
vi.mock('@/components/admin/WebhookExecutionLogDrawer', () => ({
  WebhookExecutionLogDrawer: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/useGateway', () => ({
  useWebhooks: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  deleteWebhook: vi.fn(),
}));

import { useWebhooks } from '@/hooks/useGateway';

const mockWebhooks = [
  {
    webhook_id: 'wh-deploy-notifier',
    webhook_url: 'https://example.com/hooks/deploy',
    target_session_id: 'sess-abc-123',
    auth_token: 'secret-token-1',
    payload_schema: {},
    transform_rules: {},
    enabled: true,
    created_at: '2024-01-10T00:00:00Z',
    last_triggered_at: '2024-01-15T14:00:00Z',
  },
  {
    webhook_id: 'wh-alert-handler',
    webhook_url: 'https://example.com/hooks/alerts',
    target_session_id: 'sess-def-456',
    auth_token: 'secret-token-2',
    payload_schema: {},
    transform_rules: {},
    enabled: false,
    created_at: '2024-02-05T00:00:00Z',
  },
];

describe('WebhooksTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    (useWebhooks as any).mockReturnValue({
      webhooks: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<WebhooksTable />);
    expect(screen.getByText('Loading webhooks...')).toBeInTheDocument();
  });

  it('renders webhooks data in table', () => {
    (useWebhooks as any).mockReturnValue({
      webhooks: mockWebhooks,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<WebhooksTable />);
    expect(screen.getByText('wh-deploy-notifier')).toBeInTheDocument();
    expect(screen.getByText('wh-alert-handler')).toBeInTheDocument();
    expect(screen.getByText('sess-abc-123')).toBeInTheDocument();
    expect(screen.getByText('sess-def-456')).toBeInTheDocument();
  });

  it('renders empty state with "No webhooks found."', () => {
    (useWebhooks as any).mockReturnValue({
      webhooks: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<WebhooksTable />);
    expect(screen.getByText('No webhooks found.')).toBeInTheDocument();
  });

  it('"Create Webhook" button exists', () => {
    (useWebhooks as any).mockReturnValue({
      webhooks: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<WebhooksTable />);
    expect(screen.getByRole('button', { name: /Create Webhook/i })).toBeInTheDocument();
  });

  it('search input filters webhooks', async () => {
    const user = userEvent.setup();

    (useWebhooks as any).mockReturnValue({
      webhooks: mockWebhooks,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<WebhooksTable />);

    const searchInput = screen.getByPlaceholderText('Search by webhook ID...');
    await user.type(searchInput, 'deploy');

    await waitFor(() => {
      expect(screen.getByText('wh-deploy-notifier')).toBeInTheDocument();
      expect(screen.queryByText('wh-alert-handler')).not.toBeInTheDocument();
    });
  });

  it('renders error state with retry button', () => {
    const refetchFn = vi.fn();
    (useWebhooks as any).mockReturnValue({
      webhooks: [],
      loading: false,
      error: 'Failed to fetch webhooks: 500',
      refetch: refetchFn,
    });

    render(<WebhooksTable />);
    expect(screen.getByText('Error Loading Webhooks')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });

  it('displays webhook count in footer', () => {
    (useWebhooks as any).mockReturnValue({
      webhooks: mockWebhooks,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<WebhooksTable />);
    expect(screen.getByText('2 webhook(s) total')).toBeInTheDocument();
  });
});
