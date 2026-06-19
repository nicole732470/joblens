import { createContext, useContext, useMemo, useState } from "react";

const AuthContext = createContext(null);

const TOKEN_KEY = "joblens_token";
const EMAIL_KEY = "joblens_email";

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [email, setEmail] = useState(() => localStorage.getItem(EMAIL_KEY));

  const value = useMemo(
    () => ({
      token,
      email,
      isLoggedIn: Boolean(token),
      setSession: (t, e) => {
        setToken(t);
        setEmail(e);
        localStorage.setItem(TOKEN_KEY, t);
        localStorage.setItem(EMAIL_KEY, e);
      },
      logout: () => {
        setToken(null);
        setEmail(null);
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(EMAIL_KEY);
      },
    }),
    [token, email]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
