import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { authConfig } from './config';

interface User {
  username: string;
  email: string;
}

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const TOKEN_KEY = 'auth_token';

function decodeJwtPayload(token: string): Record<string, unknown> {
  const base64Url = token.split('.')[1];
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const jsonPayload = decodeURIComponent(
    atob(base64)
      .split('')
      .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
      .join('')
  );
  return JSON.parse(jsonPayload);
}

function isTokenExpired(token: string): boolean {
  try {
    const payload = decodeJwtPayload(token);
    const exp = payload.exp as number | undefined;
    if (!exp) return true;
    return Date.now() >= exp * 1000;
  } catch {
    return true;
  }
}

function extractUserFromToken(token: string): User | null {
  try {
    const payload = decodeJwtPayload(token);
    return {
      username: (payload['cognito:username'] as string) || (payload.sub as string) || '',
      email: (payload.email as string) || '',
    };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    token: null,
    isLoading: true,
  });

  useEffect(() => {
    // Bypass authentication on localhost (local development)
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (isLocalhost) {
      setState({
        isAuthenticated: true,
        user: { username: 'local-dev', email: 'dev@localhost' },
        token: null,
        isLoading: false,
      });
      return;
    }

    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (storedToken && !isTokenExpired(storedToken)) {
      const user = extractUserFromToken(storedToken);
      setState({
        isAuthenticated: true,
        user,
        token: storedToken,
        isLoading: false,
      });
    } else {
      if (storedToken) localStorage.removeItem(TOKEN_KEY);
      setState((s) => ({ ...s, isLoading: false }));
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const endpoint = `https://cognito-idp.${authConfig.region}.amazonaws.com/`;

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
      },
      body: JSON.stringify({
        AuthFlow: 'USER_PASSWORD_AUTH',
        ClientId: authConfig.clientId,
        AuthParameters: {
          USERNAME: username,
          PASSWORD: password,
        },
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Authentication failed' }));
      throw new Error(error.message || 'Authentication failed');
    }

    const data = await response.json();
    const idToken = data.AuthenticationResult?.IdToken;

    if (!idToken) {
      throw new Error('No token received from authentication');
    }

    localStorage.setItem(TOKEN_KEY, idToken);
    const user = extractUserFromToken(idToken);

    setState({
      isAuthenticated: true,
      user,
      token: idToken,
      isLoading: false,
    });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setState({
      isAuthenticated: false,
      user: null,
      token: null,
      isLoading: false,
    });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
