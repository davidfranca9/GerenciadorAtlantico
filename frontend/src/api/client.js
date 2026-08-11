const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getToken() {
  return localStorage.getItem("token");
}

export function setToken(token) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const isJsonBody = options.body && !(options.body instanceof FormData);
  if (isJsonBody) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    body: isJsonBody ? JSON.stringify(options.body) : options.body,
  });

  if (res.status === 401) {
    setToken(null);
    window.location.href = "/login";
    throw new Error("Sessao expirada");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {
      // ignore
    }
    throw new Error(detail);
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res;
}

export async function login(email, password) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const res = await fetch(`${API_URL}/auth/login`, { method: "POST", body });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Falha no login");
  }
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export function logout() {
  setToken(null);
}

export function me() {
  return request("/auth/me");
}

export function listarAgendamentos(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/agendamentos${query}`);
}

export function criarAgendamento(payload) {
  return request("/agendamentos", { method: "POST", body: payload });
}

export function atualizarStatusAgendamento(id, status) {
  return request(`/agendamentos/${id}/status`, { method: "PATCH", body: { status } });
}

export function listarCotacoes(destino) {
  const query = destino ? `?destino=${encodeURIComponent(destino)}` : "";
  return request(`/cotacoes-frete${query}`);
}

export function cadastrarCotacao(payload) {
  return request("/cotacoes-frete", { method: "POST", body: payload });
}

async function downloadDocumento(path, payload, filename) {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Falha ao gerar documento");
  }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export function gerarOrdemColeta(payload) {
  const ext = payload.formato === "pdf" ? "pdf" : "docx";
  return downloadDocumento("/ordens-coleta/gerar", payload, `ordem_coleta.${ext}`);
}

export function gerarCartaFrete(payload) {
  const ext = payload.formato === "pdf" ? "pdf" : "docx";
  return downloadDocumento("/cartas-frete/gerar", payload, `carta_frete.${ext}`);
}
