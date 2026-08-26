import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import Icon from "./Icon";

export const NAV_SECTIONS = [
  { title: "Operação", items: [
    { to: "/dashboard", label: "Dashboard", icon: "chart", description: "Visão geral dos carregamentos da semana" },
    { to: "/pedidos", label: "Pedidos", icon: "route", description: "Pedidos disponíveis e saldo de toneladas" },
    { to: "/contrato", label: "Contratos", icon: "contract", description: "Importação e seleção de cargas" },
    { to: "/ordem-coleta", label: "Ordem de coleta", icon: "clipboard", description: "Emissão de documentos operacionais" },
    { to: "/agendamentos", label: "Agendamentos", icon: "calendar", description: "Controle de coletas programadas" },
    { to: "/analise-fretes", label: "Análise de fretes", icon: "chart", description: "Histórico e comparação de valores" },
  ]},
  { title: "Financeiro", items: [{ to: "/carta-frete", label: "Carta frete", icon: "wallet", description: "Geração de autorizações financeiras" }] },
  { title: "Comunicação", items: [
    { to: "/emails", label: "E-mails", icon: "mail", description: "Caixa de entrada do Gmail" },
    { to: "/whatsapp", label: "WhatsApp", icon: "chat", description: "Conversas e pedidos recebidos pelo WhatsApp" },
  ]},
  { title: "Integrações", items: [
    { to: "/bsoft", label: "Bsoft TMS", icon: "truck", description: "Cadastro de motoristas e veículos" },
  ]},
  { title: "Cadastros", items: [{ to: "/clientes", label: "Clientes", icon: "users", description: "Base de clientes e contatos" }] },
];
export const PAGINAS_BLOQUEAVEIS = NAV_SECTIONS.flatMap((section) => section.items);
const ALL_ITEMS = PAGINAS_BLOQUEAVEIS.concat([
  { to: "/admin", label: "Administração", icon: "settings", description: "Usuários e permissões do sistema" },
  { to: "/trocar-senha", label: "Segurança", icon: "key", description: "Atualize sua senha de acesso" },
]);

function initials(user) {
  const source = user?.name || user?.email || "?";
  return source.split(/\s|@/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const bloqueadas = user?.role === "admin" ? [] : (user?.paginas_bloqueadas || "").split(",").filter(Boolean);
  const sections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => !bloqueadas.includes(item.to)),
  })).filter((section) => section.items.length > 0);
  const sectionsExibidas = user?.role === "admin" ? [...sections, { title: "Sistema", items: [ALL_ITEMS.find((item) => item.to === "/admin")] }] : sections;
  const current = ALL_ITEMS.find((item) => item.to === location.pathname) || ALL_ITEMS[1];

  useEffect(() => setMenuOpen(false), [location.pathname]);

  if (bloqueadas.includes(location.pathname)) {
    const primeiroPermitido = sections.flatMap((s) => s.items)[0]?.to || "/trocar-senha";
    return <Navigate to={primeiroPermitido} replace />;
  }

  return (
    <div className="app-shell">
      <button className={`sidebar-backdrop ${menuOpen ? "visible" : ""}`} onClick={() => setMenuOpen(false)} aria-label="Fechar menu" />
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-logo"><img src="/logo.svg" alt="Atlântico Fertlog" /></div>
          <div className="brand-copy"><strong>ATLÂNTICO</strong><span>FERTLOG</span></div>
          <button className="icon-btn sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Fechar menu"><Icon name="close" /></button>
        </div>
        <div className="sidebar-nav">
          {sectionsExibidas.map((section) => (
            <section className="nav-section" key={section.title}>
              <div className="sidebar-caption">{section.title}</div>
              <nav>
                {section.items.map((item) => (
                  <NavLink key={item.to} to={item.to} className={({ isActive }) => `sidebar-btn${isActive ? " active" : ""}`}>
                    <span className="nav-icon"><Icon name={item.icon} /></span><span>{item.label}</span><Icon name="chevron" size={14} className="nav-chevron" />
                  </NavLink>
                ))}
              </nav>
            </section>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="user-card">
            <div className="user-avatar">{initials(user)}</div>
            <div className="user-copy"><strong>{user?.name || user?.email?.split("@")[0]}</strong><span>{user?.email}</span></div>
          </div>
          <div className="sidebar-actions">
            <NavLink to="/trocar-senha" className="icon-btn" title="Segurança"><Icon name="key" /></NavLink>
            <button className="icon-btn" onClick={toggleTheme} title={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}><Icon name={theme === "dark" ? "sun" : "moon"} /></button>
            <button className="icon-btn danger-hover" onClick={logout} title="Sair"><Icon name="logout" /></button>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <button className="icon-btn mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Abrir menu"><Icon name="menu" /></button>
            <div><span className="eyebrow">CENTRAL OPERACIONAL</span><h1>{current.label}</h1><p>{current.description}</p></div>
          </div>
          <div className="topbar-status"><span className="status-dot" /> Sistema online</div>
        </header>
        <main className={`page-content page-${location.pathname.slice(1) || "home"}`}><Outlet /></main>
      </div>
    </div>
  );
}
