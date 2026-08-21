const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getToken() {
  return localStorage.getItem("token");
}

export function setToken(token) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
}

export function hasToken() {
  return Boolean(getToken());
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
    const hadToken = hasToken();
    setToken(null);
    if (hadToken && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
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

export function obterAgendamento(id) {
  return request(`/agendamentos/${id}`);
}

export function listarCotacoes(destino) {
  const query = destino ? `?destino=${encodeURIComponent(destino)}` : "";
  return request(`/cotacoes-frete${query}`);
}

export function cadastrarCotacao(payload) {
  return request("/cotacoes-frete", { method: "POST", body: payload });
}

export function listarClientes(busca) {
  const query = busca ? `?busca=${encodeURIComponent(busca)}` : "";
  return request(`/clientes${query}`);
}

export function criarCliente(payload) {
  return request("/clientes", { method: "POST", body: payload });
}

export function atualizarCliente(id, payload) {
  return request(`/clientes/${id}`, { method: "PUT", body: payload });
}

export function removerCliente(id) {
  return request(`/clientes/${id}`, { method: "DELETE" });
}

export function changePassword(currentPassword, newPassword) {
  return request("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export function adminListarUsuarios() {
  return request("/admin/usuarios");
}

export function adminCriarUsuario(payload) {
  return request("/admin/usuarios", { method: "POST", body: payload });
}

export function adminAtualizarUsuario(id, payload) {
  return request(`/admin/usuarios/${id}`, { method: "PATCH", body: payload });
}

async function uploadFile(path, file) {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Falha no upload");
  }
  return res.json();
}

async function uploadFiles(path, files) {
  const token = getToken();
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Falha no upload");
  }
  return res.json();
}

export function ocrPedidoHeringer(file) {
  return uploadFile("/contrato/ocr/pedido-heringer", file);
}

export function ocrCnh(file) {
  return uploadFile("/contrato/ocr/cnh", file);
}

export function ocrCrlv(file) {
  return uploadFile("/contrato/ocr/crlv", file);
}

export function parsePdfPedido(file) {
  return uploadFile("/contrato/parse-pdf", file);
}

export function bsoftLookups() {
  return request("/bsoft/lookups");
}

export function listarEmails(pagina = 1, tamanhoPagina = 25) {
  return request(`/email/mensagens?pagina=${pagina}&tamanho_pagina=${tamanhoPagina}`);
}

export function obterEmail(id) {
  return request(`/email/mensagens/${encodeURIComponent(id)}`);
}

export async function enviarEmail({ destinatarios, assunto, corpo, anexos }) {
  const token = getToken();
  const formData = new FormData();
  formData.append("destinatarios", destinatarios.join(","));
  formData.append("assunto", assunto || "");
  formData.append("corpo", corpo || "");
  for (const arquivo of anexos || []) formData.append("anexos", arquivo);
  const res = await fetch(`${API_URL}/email/enviar`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Falha ao enviar e-mail");
  }
  return res.json();
}

export function bsoftCidades() {
  return request("/bsoft/cidades");
}

export function bsoftConsultaCep(cep) {
  return request(`/bsoft/consulta-cep/${encodeURIComponent(cep)}`);
}

export function bsoftConsultaCnpj(cnpj) {
  return request(`/bsoft/consulta-cnpj/${encodeURIComponent(cnpj)}`);
}

export function bsoftBuscarPessoaFisica(cpf) {
  return request(`/bsoft/pessoas/fisicas/${encodeURIComponent(cpf)}/busca`);
}

export function bsoftBuscarPessoaJuridica(cnpj) {
  return request(`/bsoft/pessoas/juridicas/${encodeURIComponent(cnpj)}/busca`);
}

export function bsoftImportarOC(file) {
  return uploadFile("/bsoft/importar-oc", file);
}

export function bsoftImportarDocumentos(files) {
  return uploadFiles("/bsoft/importar-documentos", files);
}

export function bsoftCadastrarPessoaFisica(payload) {
  return request("/bsoft/pessoas/fisicas", { method: "POST", body: payload });
}

export function bsoftCadastrarVeiculo(payload) {
  return request("/bsoft/veiculos", { method: "POST", body: payload });
}

export function bsoftCadastrarCompleto(payload) {
  return request("/bsoft/cadastrar-completo", { method: "POST", body: payload });
}

export function buonnyLookups() {
  return request("/buonny/lookups");
}

export function buonnyLogin(username, password) {
  return request("/buonny/login", { method: "POST", body: { username, password } });
}

export function buonnyConsultar(payload) {
  return request("/buonny/consultar", { method: "POST", body: payload });
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
  const disposition = res.headers.get("content-disposition") || "";
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  let finalFilename = filename;
  if (utf8Match) {
    finalFilename = decodeURIComponent(utf8Match[1]);
  } else if (plainMatch) {
    finalFilename = plainMatch[1];
  }
  const agendamentoIdHeader = res.headers.get("x-agendamento-id");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = finalFilename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
  return { agendamentoId: agendamentoIdHeader ? Number(agendamentoIdHeader) : null };
}

export function gerarOrdemColeta(payload) {
  return downloadDocumento("/ordens-coleta/gerar", payload, "ordem_coleta.pdf");
}

export function gerarAutorizacaoColeta(payload) {
  return downloadDocumento("/ordens-coleta/gerar-autorizacao", payload, "autorizacao_coleta.xlsx");
}

export function enviarOrdemColetaEmail(payload) {
  return request("/ordens-coleta/enviar-email", { method: "POST", body: payload });
}

export function gerarCartaFrete(payload) {
  const ext = payload.formato === "pdf" ? "pdf" : "docx";
  return downloadDocumento("/cartas-frete/gerar", payload, `carta_frete.${ext}`);
}
