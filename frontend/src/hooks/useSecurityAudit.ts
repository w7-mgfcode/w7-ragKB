/**
 * Custom hook for managing security audit log data
 * 
 * Provides:
 * - Fetching security audit events with filters
 * - Auto-refresh capability
 * - Loading and error states
 * - Export functionality
 */

import { useState, useEffect, useCallback } from 'react';
import { listSecurityAuditEvents, exportSecurityAuditLog } from '@/lib/api';
import type { SecurityAuditEvent, SecurityAuditFilters } from '@/types/gateway';

interface UseSecurityAuditOptions {
  autoRefresh?: boolean;
  refreshInterval?: number; // milliseconds
  initialFilters?: SecurityAuditFilters;
}

export function useSecurityAudit(options: UseSecurityAuditOptions = {}) {
  const {
    autoRefresh = false,
    refreshInterval = 30000, // 30 seconds default
    initialFilters = {},
  } = options;

  const [events, setEvents] = useState<SecurityAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<SecurityAuditFilters>(initialFilters);

  const fetchEvents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listSecurityAuditEvents(filters);
      setEvents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch security audit events');
      console.error('Error fetching security audit events:', err);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const exportLog = useCallback(async () => {
    try {
      const blob = await exportSecurityAuditLog(filters);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `security-audit-log-${new Date().toISOString()}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to export security audit log');
    }
  }, [filters]);

  const updateFilters = useCallback((newFilters: Partial<SecurityAuditFilters>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({});
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchEvents();
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, fetchEvents]);

  return {
    events,
    loading,
    error,
    filters,
    updateFilters,
    clearFilters,
    refetch: fetchEvents,
    exportLog,
  };
}
