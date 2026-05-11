/**
 * Custom hook for DM Pairing data management
 * 
 * Provides access to channel users, approval history, and approval actions.
 */

import { useState, useEffect, useCallback } from 'react';
import { listChannelUsers, getApprovalHistory } from '@/lib/api';
import type { ChannelUser, ApprovalEvent, DMPairingFilters } from '@/types/gateway';

export function useChannelUsers(filters?: DMPairingFilters) {
  const [users, setUsers] = useState<ChannelUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listChannelUsers(filters);
      setUsers(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filters?.channel_id, filters?.approved, filters?.search]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  return { users, loading, error, refetch: fetchUsers };
}

export function useApprovalHistory(filters?: { channel_id?: string; start_date?: string; end_date?: string }) {
  const [history, setHistory] = useState<ApprovalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getApprovalHistory(filters);
      setHistory(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filters?.channel_id, filters?.start_date, filters?.end_date]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  return { history, loading, error, refetch: fetchHistory };
}
