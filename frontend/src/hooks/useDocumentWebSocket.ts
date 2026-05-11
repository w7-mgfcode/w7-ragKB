/**
 * WebSocket hook for real-time document sync updates.
 *
 * Connects to the documents WebSocket endpoint, auto-reconnects with
 * exponential backoff, and invalidates React Query cache on events.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getAccessToken } from '@/lib/auth-client';

export type ConnectionStatus = 'connected' | 'disconnected' | 'reconnecting';

interface WebSocketMessage {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

const MIN_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;

export function useDocumentWebSocket(enabled: boolean = true) {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const mountedRef = useRef(true);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectDelayRef = useRef(MIN_RECONNECT_DELAY);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');

  const invalidateDocuments = useCallback(
    (filePath?: string) => {
      queryClient.invalidateQueries({ queryKey: ['documents', 'tree'] });
      queryClient.invalidateQueries({ queryKey: ['documents', 'stats'] });
      queryClient.invalidateQueries({ queryKey: ['documents', 'sync-statuses'] });
      if (filePath) {
        queryClient.invalidateQueries({
          queryKey: ['documents', 'document', filePath],
        });
        queryClient.invalidateQueries({
          queryKey: ['documents', 'sync-status', filePath],
        });
      }
    },
    [queryClient],
  );

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        const filePath = msg.data?.file_path as string | undefined;

        switch (msg.type) {
          case 'document_created':
          case 'document_updated':
          case 'document_deleted':
            invalidateDocuments(filePath);
            break;
          case 'sync_status_update':
            queryClient.invalidateQueries({
              queryKey: ['documents', 'sync-statuses'],
            });
            if (filePath) {
              queryClient.invalidateQueries({
                queryKey: ['documents', 'sync-status', filePath],
              });
            }
            break;
          case 'reindex_complete':
            invalidateDocuments(filePath);
            break;
        }
      } catch {
        // Ignore malformed messages
      }
    },
    [invalidateDocuments, queryClient],
  );

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return;

    const token = getAccessToken();
    if (!token) {
      setStatus('disconnected');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const apiBase = import.meta.env.VITE_API_BASE_URL || '';
    let wsUrl: string;

    if (apiBase) {
      // Absolute API base — replace protocol
      wsUrl = `${apiBase.replace(/^https?:/, protocol)}/api/documents/ws?token=${encodeURIComponent(token)}`;
    } else {
      wsUrl = `${protocol}//${window.location.host}/api/documents/ws?token=${encodeURIComponent(token)}`;
    }

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close();
          return;
        }
        setStatus('connected');
        reconnectDelayRef.current = MIN_RECONNECT_DELAY;
      };

      ws.onmessage = handleMessage;

      ws.onclose = () => {
        wsRef.current = null;
        if (!mountedRef.current) return;
        setStatus('reconnecting');
        const delay = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // onclose will fire after this — reconnect handled there
      };
    } catch {
      setStatus('disconnected');
    }
  }, [enabled, handleMessage]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setStatus('disconnected');
    };
  }, [connect, enabled]);

  return { status };
}
