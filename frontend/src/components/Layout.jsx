import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import Icon from "./Icon";
import * as api from "../api/client";

// Quem decide quais telas existem e quem pode ver cada uma e o backend
// (backend/app/auth.py, GRUPOS_TELAS): e a mesma lista que recusa as rotas com
// 403. Aqui ficam os grupos na ordem do menu com icone e descricao de cada aba,
// e o teste backend/tests/test_permissao_telas.py confere que as duas listas
// batem - aba nova tem que entrar nos dois lugares, senao a suite reclama.
export const NAV_SECTIONS = [
  { title: "Operação", items: [
    { to: "/dashboard", label: "Dashboard", icon: "chart", description: "Visão geral dos carregamentos da semana" },
    { to: "/pedidos", label: "Pedidos", icon: "route", description: "Pedidos disponíveis e saldo de toneladas" },
    { to: "/contrato", label: "Contratos", icon: "contract", description: "Importação e seleção de cargas" },
    { to: "/ordem-coleta", label: "Ordem de coleta", icon: "clipboard", description: "Emissão de documentos operacionais" },
    { to: "/autorizacao-abastecimento", label: "Autorização de abastecimento", icon: "file", description: "Geração e envio das autorizações de abastecimento" },
    { to: "/agendamentos", label: "Agendamentos", icon: "calendar", description: "Controle de coletas programadas" },
    { to: "/analise-fretes", label: "Análise de fretes", icon: "chart", description: "Histórico e comparação de valores" },
    { to: "/documentos-fiscais", label: "Documentos fiscais", icon: "file", description: "CT-e e CIOT emitidos, vindos do Bsoft" },
  ]},
  { title: "Financeiro", items: [
    // Aba liberada aqui da acesso de VISUALIZACAO: o backend responde os GET
    // dessas telas, mas lancar, pagar e excluir seguem so com administrador.
    { to: "/financeiro/caixa", label: "Caixa", icon: "wallet", description: "Saldo dos bancos e movimentações do dia" },
    { to: "/financeiro/carregamentos", label: "Carregamentos", icon: "truck", description: "Como foi cada carga: frete, motorista, agenciamento, comissão e sobra" },
    { to: "/financeiro/lucro-bruto", label: "Lucro bruto", icon: "trend", description: "Resumo do mês: meta, para onde foi o frete e sobra" },
    { to: "/financeiro/gastos", label: "Gastos", icon: "clipboard", description: "Despesas da empresa e gastos pessoais do mês" },
    { to: "/financeiro/precificacao", label: "Precificação CT-e", icon: "chart", description: "Custo fixo por tonelada e frete mínimo" },
    { to: "/financeiro/pagamentos", label: "Pagamentos", icon: "calendar", description: "Vencimentos do mês, semana a semana" },
    { to: "/financeiro/faturas", label: "Faturas de abastecimento", icon: "file", description: "Previsão e pagamento das faturas de abastecimento" },
    { to: "/financeiro/agenciamentos", label: "Agenciamentos", icon: "users", description: "Agenciamentos automáticos dos carregamentos e pagamentos" },
    { to: "/financeiro/dividas", label: "Dívidas ativas", icon: "coins", description: "Quanto falta e quando se paga cada dívida" },
  ] },
  { title: "Comunicação", items: [
    { to: "/emails", label: "E-mails", icon: "mail", description: "Recebidos e enviados do Gmail" },
    { to: "/whatsapp", label: "WhatsApp", icon: "chat", description: "Conversas e pedidos recebidos pelo WhatsApp" },
  ]},
  { title: "Integrações", items: [
    { to: "/bsoft", label: "Bsoft TMS", icon: "truck", description: "Cadastro de motoristas e veículos" },
  ]},
  { title: "Cadastros", items: [{ to: "/clientes", label: "Clientes", icon: "users", description: "Base de clientes e contatos" }] },
  { title: "Sistema", items: [
    // adminOnly: mexe no sistema inteiro (usuarios, senhas, listas de e-mail) e
    // o backend dessas areas exige administrador - nao da pra liberar por usuario.
    { to: "/admin", label: "Administração", icon: "users", description: "Usuários e permissões do sistema", adminOnly: true },
    { to: "/configuracoes", label: "Configurações", icon: "settings", description: "Listas de e-mail e outros ajustes do sistema", adminOnly: true },
    // A propria senha e de todo mundo, e ja tem o atalho no pe da barra: nao
    // precisa virar item de menu.
    { to: "/trocar-senha", label: "Segurança", icon: "key", description: "Atualize sua senha de acesso", sempreLiberada: true, foraDoMenu: true },
  ] },
];
const ALL_ITEMS = NAV_SECTIONS.flatMap((section) => section.items);

function initials(user) {
  const source = user?.name || user?.email || "?";
  return source.split(/\s|@/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

// Conta os e-mails chegados desde a ultima vez que a aba foi aberta. A
// marca da visita fica no navegador, entao o contador zera sozinho quando
// alguem entra em E-mails.
function useEmailsNovos() {
  const [novos, setNovos] = useState(0);

  useEffect(() => {
    let vivo = true;

    async function conferir() {
      let desde;
      try {
        desde = Number(localStorage.getItem("emailUltimaVisita"));
      } catch {
        return;
      }
      if (!desde) {
        // Primeira vez: marca agora e nao acusa nada como novo.
        try {
          localStorage.setItem("emailUltimaVisita", String(Date.now()));
        } catch {
          /* sem storage, o contador so nao funciona */
        }
        return;
      }
      try {
        const dados = await api.contarEmailsNovos(desde);
        if (vivo) setNovos(dados.novos || 0);
      } catch {
        /* contador e informativo: falha nao aparece na tela */
      }
    }

    conferir();
    const timer = setInterval(conferir, 60000);
    const aoVisitar = () => setNovos(0);
    window.addEventListener("emailVisitado", aoVisitar);
    return () => {
      vivo = false;
      clearInterval(timer);
      window.removeEventListener("emailVisitado", aoVisitar);
    };
  }, []);

  return novos;
}

// Notas fiscais que chegaram e ainda nao viraram CT-e. Diferente do
// contador de e-mails, nao e "desde a ultima visita": e uma fila de
// trabalho, e fica visivel enquanto houver algo nela.
function useNotasSemCte() {
  const [contagem, setContagem] = useState({ sem_cte: 0, casadas: 0 });

  useEffect(() => {
    let vivo = true;
    async function conferir() {
      try {
        const dados = await api.fiscalContarNotas();
        if (vivo) setContagem(dados);
      } catch {
        /* contador e informativo */
      }
    }
    conferir();
    const timer = setInterval(conferir, 60000);
    return () => {
      vivo = false;
      clearInterval(timer);
    };
  }, []);

  return contagem;
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const emailsNovos = useEmailsNovos();
  const notas = useNotasSemCte();
  // Lista de permissao: aba que nao esta liberada pro usuario nao aparece.
  // Administrador ve tudo, e e por isso que nem precisa de lista.
  const admin = user?.role === "admin";
  const liberadas = (user?.paginas_liberadas || "").split(",").filter(Boolean);
  const podeVer = (item) => admin || (!item.adminOnly && (item.sempreLiberada || liberadas.includes(item.to)));
  const sectionsExibidas = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => !item.foraDoMenu && podeVer(item)),
  })).filter((section) => section.items.length > 0);
  const current = ALL_ITEMS.find((item) => item.to === location.pathname) || ALL_ITEMS[1];

  useEffect(() => setMenuOpen(false), [location.pathname]);

  // O backend recusa de verdade (403), mas a tela tambem nao deve abrir: quem
  // digita o endereco de uma aba que nao tem (ou perdeu o acesso) volta pra
  // primeira que ele ve. Endereco que nao e aba do menu passa direto.
  const telaAtual = ALL_ITEMS.find((item) => item.to === location.pathname);
  if (telaAtual && !podeVer(telaAtual)) {
    const primeiroPermitido = sectionsExibidas.flatMap((s) => s.items)[0]?.to || "/trocar-senha";
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
                    <span className="nav-icon"><Icon name={item.icon} /></span>
                    <span>{item.label}</span>
                    {item.to === "/documentos-fiscais" && notas.sem_cte > 0 && (
                      <span
                        title={`${notas.sem_cte} nota${notas.sem_cte === 1 ? "" : "s"} sem CT-e${notas.casadas ? ` (${notas.casadas} já casada${notas.casadas === 1 ? "" : "s"} com agendamento)` : ""}`}
                        style={{
                          marginLeft: "auto", background: "var(--accent, #2f9e6d)", color: "#fff",
                          borderRadius: 999, fontSize: 11, fontWeight: 700, lineHeight: 1,
                          padding: "3px 7px", fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {notas.sem_cte > 99 ? "99+" : notas.sem_cte}
                      </span>
                    )}
                    {item.to === "/emails" && emailsNovos > 0 && (
                      <span
                        title={`${emailsNovos} e-mail${emailsNovos === 1 ? "" : "s"} desde sua ultima visita`}
                        style={{
                          marginLeft: "auto", background: "var(--accent, #2f9e6d)", color: "#fff",
                          borderRadius: 999, fontSize: 11, fontWeight: 700, lineHeight: 1,
                          padding: "3px 7px", fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {emailsNovos > 99 ? "99+" : emailsNovos}
                      </span>
                    )}
                    <Icon name="chevron" size={14} className="nav-chevron" />
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
