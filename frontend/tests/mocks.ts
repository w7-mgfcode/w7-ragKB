import { Page } from '@playwright/test';

// Mock data matching the AuthUser / AuthSession shapes from database.types.ts
export const mockUser = {
  id: 'test-user-123',
  email: 'test@example.com',
  full_name: 'Test User',
  avatar_url: null,
  is_admin: false,
};

export const mockSession = {
  access_token: 'mock-access-token',
  user: mockUser,
};

// ---------------------------------------------------------------------------
// Authenticated state — intercepts backend auth/API endpoints
// ---------------------------------------------------------------------------

export async function setupAuthenticatedMocks(page: Page) {
  // /api/auth/refresh — returns a valid session
  await page.route('**/api/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockSession),
    });
  });

  // /api/auth/me — returns the current user profile
  await page.route('**/api/auth/me', async (route) => {
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...mockUser, ...body }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockUser),
      });
    }
  });

  // /api/auth/logout
  await page.route('**/api/auth/logout', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });

  // /api/conversations
  await page.route('**/api/conversations', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // /api/admin/status
  await page.route('**/api/admin/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ is_admin: false }),
    });
  });
}

// ---------------------------------------------------------------------------
// Unauthenticated state — refresh fails, login/register succeed
// ---------------------------------------------------------------------------

export async function setupUnauthenticatedMocks(page: Page) {
  // Refresh fails — no active session
  await page.route('**/api/auth/refresh', async (route) => {
    await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Invalid or expired refresh token"}' });
  });

  // Login succeeds with any credentials
  await page.route('**/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockSession),
    });
  });

  // Register succeeds
  await page.route('**/api/auth/register', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockSession),
    });
  });

  // /api/auth/me — returns user after login
  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockUser),
    });
  });
}

// ---------------------------------------------------------------------------
// Agent API mock (streaming)
// ---------------------------------------------------------------------------

export async function setupAgentAPIMocks(page: Page) {
  await page.route('**/api/pydantic-agent', async (route) => {
    const mockResponse = `{"text": "Hello! I'm a mock AI assistant."}
{"complete": true, "session_id": "session-new", "conversation_title": "New Chat"}`;

    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
        'Cache-Control': 'no-cache',
      },
      body: mockResponse,
    });
  });
}

// ---------------------------------------------------------------------------
// Gateway API mocks — intercepts OpenClaw gateway endpoints
// ---------------------------------------------------------------------------

export async function setupGatewayMocks(page: Page) {
  // Mock channels endpoint
  await page.route('**/api/gateway/channels', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            channel_id: 'slack-main',
            channel_type: 'slack',
            status: 'connected',
            enabled: true,
            config: { api_token: '***', rate_limit_per_minute: 45 },
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
          {
            channel_id: 'telegram-bot',
            channel_type: 'telegram',
            status: 'connected',
            enabled: true,
            config: { api_token: '***', rate_limit_per_minute: 30 },
            created_at: '2024-01-02T00:00:00Z',
            updated_at: '2024-01-02T00:00:00Z',
          },
        ]),
      });
    } else {
      await route.fulfill({ status: 201, contentType: 'application/json', body: '{}' });
    }
  });

  // Mock sessions
  await page.route('**/api/gateway/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          session_id: 'sess-001',
          channel_id: 'slack-main',
          user_id: 'user-1',
          session_type: 'direct_message',
          activation_mode: 'auto',
          message_count: 25,
          memory_usage: 42,
          last_activity_at: new Date().toISOString(),
          created_at: '2024-01-01T00:00:00Z',
        },
      ]),
    });
  });

  // Mock webhooks
  await page.route('**/api/gateway/webhooks', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          webhook_id: 'github-alerts',
          target_session_id: 'sess-001',
          auth_token: 'token-abc',
          webhook_url: '/api/gateway/webhooks/github-alerts/trigger',
          enabled: true,
          created_at: '2024-01-01T00:00:00Z',
        },
      ]),
    });
  });

  // Mock cron jobs
  await page.route('**/api/gateway/cron-jobs', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          cron_job_id: 'daily-summary',
          schedule: '0 9 * * *',
          target_session_id: 'sess-001',
          message_template: 'Generate daily summary',
          timezone: 'UTC',
          enabled: true,
          last_execution: null,
          next_execution: new Date(Date.now() + 86400000).toISOString(),
          created_at: '2024-01-01T00:00:00Z',
        },
      ]),
    });
  });

  // Mock gateway metrics (the real getGatewayMetrics calls /api/admin/monitor/gateway)
  await page.route('**/api/admin/monitor/gateway**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        active_sessions: 5,
        channels: [
          {
            channel_id: 'slack-main',
            channel_type: 'slack',
            status: 'connected',
            is_connected: true,
            messages_sent: 100,
            messages_received: 50,
            error_count: 0,
            queue_depth: 2,
          },
          {
            channel_id: 'telegram-bot',
            channel_type: 'telegram',
            status: 'connected',
            is_connected: true,
            messages_sent: 50,
            messages_received: 25,
            error_count: 0,
            queue_depth: 1,
          },
        ],
      }),
    });
  });

  // Mock metrics endpoint (legacy format, for components using /api/gateway/metrics)
  await page.route('**/api/gateway/metrics**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        active_sessions: 5,
        queue_depth: 3,
        messages_per_channel: { 'slack-main': 150, 'telegram-bot': 75 },
        channel_health: { 'slack-main': 'connected', 'telegram-bot': 'connected' },
        timestamp: new Date().toISOString(),
      }),
    });
  });

  // Mock cron preview
  await page.route('**/api/gateway/cron-jobs/preview**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        is_valid: true,
        next_executions: [
          new Date(Date.now() + 3600000).toISOString(),
          new Date(Date.now() + 7200000).toISOString(),
          new Date(Date.now() + 10800000).toISOString(),
          new Date(Date.now() + 14400000).toISOString(),
          new Date(Date.now() + 18000000).toISOString(),
        ],
      }),
    });
  });

  // Mock channel test connection
  await page.route('**/api/gateway/channels/*/test', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, message: 'Connection successful' }),
    });
  });

  // Mock browser instances
  await page.route('**/api/gateway/browser-instances', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  // Mock delete endpoints for channels
  await page.route('**/api/gateway/channels/*', async (route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    } else {
      await route.continue();
    }
  });
}

// ---------------------------------------------------------------------------
// Document API mocks — intercepts document browser endpoints
// ---------------------------------------------------------------------------

export const mockDocumentTree = [
  {
    type: 'directory',
    name: 'security',
    path: 'security',
    children: [
      {
        type: 'document',
        name: 'auth-guide.md',
        path: 'security/auth-guide.md',
        metadata: { size: 2048, modified: '2026-02-20T10:00:00Z', word_count: 350 },
      },
      {
        type: 'document',
        name: 'rbac.md',
        path: 'security/rbac.md',
        metadata: { size: 1024, modified: '2026-02-18T10:00:00Z', word_count: 200 },
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
        name: 'deployment.md',
        path: 'operations/deployment.md',
        metadata: { size: 3072, modified: '2026-02-15T10:00:00Z', word_count: 500 },
      },
    ],
  },
  {
    type: 'document',
    name: 'readme.md',
    path: 'readme.md',
    metadata: { size: 512, modified: '2026-02-25T10:00:00Z', word_count: 80 },
  },
];

export const mockDocumentStats = {
  total_directories: 2,
  total_documents: 4,
  total_subdirectories: 0,
  total_words: 1130,
};

export async function setupDocumentMocks(page: Page) {
  // Register generic catch-all FIRST (lowest priority in Playwright's last-wins model)
  await page.route('**/api/documents/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (method === 'GET') {
      const path = decodeURIComponent(url.split('/api/documents/')[1]);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          path,
          content: `# ${path.split('/').pop()?.replace('.md', '')}\n\nDocument content for ${path}.`,
          metadata: { size: 1024, modified: '2026-02-20T10:00:00Z', word_count: 100 },
        }),
      });
      return;
    }

    if (method === 'POST') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          path: body.path,
          content: body.content,
          metadata: { size: body.content.length, modified: new Date().toISOString(), word_count: body.content.split(/\s+/).length },
        }),
      });
      return;
    }

    if (method === 'PUT') {
      const body = route.request().postDataJSON();
      const path = decodeURIComponent(url.split('/api/documents/')[1]);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          path,
          content: body.content,
          metadata: { size: body.content.length, modified: new Date().toISOString(), word_count: body.content.split(/\s+/).length },
        }),
      });
      return;
    }

    if (method === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Deleted', path: 'deleted.md' }),
      });
      return;
    }

    await route.continue();
  });

  // Register specific routes LAST (highest priority — Playwright uses last-registered-wins)

  // Directories endpoint
  await page.route('**/api/documents/directories', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(['security', 'operations']),
      });
    } else {
      await route.fulfill({ status: 201, contentType: 'application/json', body: '{}' });
    }
  });

  // Bulk move endpoint
  await page.route('**/api/documents/bulk-move', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ successful: [], failed: [] }),
    });
  });

  // Bulk delete endpoint
  await page.route('**/api/documents/bulk-delete', async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ successful: body.paths, failed: [] }),
    });
  });

  // Search endpoint
  await page.route('**/api/documents/search', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          path: 'security/auth-guide.md',
          name: 'auth-guide.md',
          matches: [{ type: 'content', snippet: 'matching content', position: 10 }],
          metadata: { size: 2048, modified: '2026-02-20T10:00:00Z', word_count: 350 },
        },
      ]),
    });
  });

  // Stats endpoint
  await page.route('**/api/documents/stats', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockDocumentStats),
    });
  });

  // Tree endpoint (registered LAST = highest priority)
  await page.route('**/api/documents/tree', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockDocumentTree),
    });
  });
}

// ---------------------------------------------------------------------------
// Convenience: set up everything for an authenticated test
// ---------------------------------------------------------------------------

export async function setupAllMocks(page: Page) {
  await setupAuthenticatedMocks(page);
  await setupAgentAPIMocks(page);
  await setupGatewayMocks(page);
}

// Backward-compatible helper used by E2E specs.
export async function setupModuleMocks(_page: Page) {
  // No module-level browser mocks are currently required.
}
