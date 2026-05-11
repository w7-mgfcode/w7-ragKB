import { useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth-client';
import { useAuth } from './useAuth';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export const useAdmin = () => {
  const { user } = useAuth();
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAdminStatus = async () => {
      if (!user) {
        setIsAdmin(false);
        setLoading(false);
        return;
      }

      try {
        const res = await authFetch(`${API_BASE}/api/admin/status`);
        if (!res.ok) {
          console.error('Error checking admin status:', res.status);
          setIsAdmin(false);
        } else {
          const data = await res.json();
          setIsAdmin(data?.is_admin || false);
        }
      } catch (error) {
        console.error('Error checking admin status:', error);
        setIsAdmin(false);
      } finally {
        setLoading(false);
      }
    };

    checkAdminStatus();
  }, [user]);

  return { isAdmin, loading };
};
