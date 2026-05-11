import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { setAccessToken, fetchCurrentUser } from '@/lib/auth-client';
import { Loader } from 'lucide-react';

/**
 * Handles the OAuth callback redirect from the backend.
 * Reads access_token (or error) from URL query params, stores the token,
 * validates it by fetching the user profile, then navigates to home.
 */
export const AuthCallback = () => {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleAuthCallback = async () => {
      const params = new URLSearchParams(window.location.search);

      const errorParam = params.get('error');
      if (errorParam) {
        setError(decodeURIComponent(errorParam));
        return;
      }

      const accessToken = params.get('access_token');
      if (!accessToken) {
        setError('No authentication token received.');
        return;
      }

      try {
        setAccessToken(accessToken);
        await fetchCurrentUser(); // validate the token works
        navigate('/');
      } catch {
        setError('Authentication failed. Please try again.');
      }
    };

    handleAuthCallback();
  }, [navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      {error ? (
        <div className="text-center">
          <h2 className="text-xl font-semibold text-red-500 mb-2">Authentication Error</h2>
          <p className="text-gray-600 dark:text-gray-400">{error}</p>
          <button
            className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            onClick={() => navigate('/login')}
          >
            Return to Login
          </button>
        </div>
      ) : (
        <div className="text-center">
          <Loader className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-500" />
          <p className="text-gray-600 dark:text-gray-400">Completing authentication...</p>
        </div>
      )}
    </div>
  );
};

export default AuthCallback;
