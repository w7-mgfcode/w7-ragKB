import { useEffect, useState, createContext, useContext, ReactNode } from 'react';
import {
  login,
  register,
  logout,
  refreshToken,
  resetPassword as resetPasswordApi,
  fetchCurrentUser,
  setAccessToken,
  AuthError,
} from '../lib/auth-client';
import type { AuthSession, AuthUser } from '../types/database.types';
import { useToast } from '@/hooks/use-toast';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

interface AuthProviderProps {
  children: ReactNode;
}

interface AuthContextType {
  session: AuthSession | null;
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: Error | null }>;
  signInWithGoogle: () => Promise<{ error: Error | null }>;
  signUp: (email: string, password: string) => Promise<{ error: Error | null; data: unknown }>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ error: Error | null }>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: AuthProviderProps) => {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  // Restore session on mount via refresh token cookie
  useEffect(() => {
    const restoreSession = async () => {
      try {
        const refreshed = await refreshToken();
        if (refreshed) {
          const currentUser = await fetchCurrentUser();
          setUser(currentUser);
          setSession({ access_token: '', user: currentUser });
        }
      } catch {
        // No valid session — user will need to sign in
      } finally {
        setLoading(false);
      }
    };

    restoreSession();
  }, []);

  const signIn = async (email: string, password: string) => {
    try {
      const data = await login(email, password);
      setSession(data);
      setUser(data.user);
      return { error: null };
    } catch (error) {
      toast({
        title: 'Authentication error',
        description: (error as Error)?.message || 'Failed to sign in',
        variant: 'destructive',
      });
      return { error: error as Error };
    }
  };

  const signInWithGoogle = async () => {
    try {
      window.location.href = `${API_BASE}/api/auth/google`;
      return { error: null };
    } catch (error) {
      toast({
        title: 'Google authentication error',
        description: (error as Error)?.message || 'Failed to sign in with Google',
        variant: 'destructive',
      });
      return { error: error as Error };
    }
  };

  const signUp = async (email: string, password: string) => {
    try {
      const data = await register(email, password);
      setSession(data);
      setUser(data.user);
      toast({
        title: 'Account created',
        description: 'You have been signed in.',
      });
      return { error: null, data };
    } catch (error) {
      toast({
        title: 'Sign up error',
        description: (error as Error)?.message || 'Failed to sign up',
        variant: 'destructive',
      });
      return { error: error as Error, data: null };
    }
  };

  const signOut = async () => {
    try {
      await logout();
    } catch {
      // Best-effort logout — clear local state regardless
    }
    setAccessToken(null);
    setSession(null);
    setUser(null);
    toast({
      title: 'Signed out',
      description: 'You have been signed out.',
    });
  };

  const resetPasswordHandler = async (email: string) => {
    try {
      await resetPasswordApi(email);
      toast({
        title: 'Password reset email sent',
        description: 'Check your email for the password reset link.',
      });
      return { error: null };
    } catch (error) {
      toast({
        title: 'Reset password error',
        description: (error as Error)?.message || 'Failed to send reset password email',
        variant: 'destructive',
      });
      return { error: error as Error };
    }
  };

  const value: AuthContextType = {
    session,
    user,
    loading,
    signIn,
    signInWithGoogle,
    signUp,
    signOut,
    resetPassword: resetPasswordHandler,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
