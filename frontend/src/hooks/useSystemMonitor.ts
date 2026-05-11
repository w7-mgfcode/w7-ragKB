import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '@/lib/auth-client';
import type { SystemMonitorData } from '@/types/systemMonitor';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export function useSystemMonitor() {
  const [data, setData] = useState<SystemMonitorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/api/admin/monitor/all`);
      if (!res.ok) {
        throw new Error(`Failed to fetch monitor data: ${res.status}`);
      }
      const json = await res.json();
      setData(json);
      setLastUpdated(new Date());
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      console.error('System monitor fetch failed:', message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData, lastUpdated };
}
