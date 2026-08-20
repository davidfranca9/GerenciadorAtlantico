import { createContext, useContext, useEffect, useState } from "react";
import * as api from "../api/client";

const AuthContext = createContext(null);

const isLoopback = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const localPreview = import.meta.env.VITE_LOCAL_PREVIEW === "true" && isLoopback;
const previewUser = { email: import.meta.env.VITE_PREVIEW_EMAIL, name: "Administrador Preview", role: "admin" };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (localPreview && new URLSearchParams(window.location.search).get("preview") === "1") {
      sessionStorage.setItem("local-preview-auth", "true");
      setUser(previewUser);
      setLoading(false);
      return;
    }
    if (localPreview && sessionStorage.getItem("local-preview-auth") === "true") {
      setUser(previewUser);
      setLoading(false);
      return;
    }
    if (!api.hasToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  async function doLogin(email, password) {
    const normalizedEmail = String(email || "").trim().toLowerCase();
    const normalizedPassword = String(password || "").trim();
    if (
      localPreview &&
      normalizedEmail === String(import.meta.env.VITE_PREVIEW_EMAIL || "").trim().toLowerCase() &&
      normalizedPassword === String(import.meta.env.VITE_PREVIEW_PASSWORD || "").trim()
    ) {
      sessionStorage.setItem("local-preview-auth", "true");
      setUser(previewUser);
      return previewUser;
    }
    await api.login(normalizedEmail, password);
    const currentUser = await api.me();
    setUser(currentUser);
    return currentUser;
  }

  function doLogout() {
    sessionStorage.removeItem("local-preview-auth");
    api.logout();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login: doLogin, logout: doLogout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
