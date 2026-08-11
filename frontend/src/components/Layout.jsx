import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV_SECTIONS = [
  {
    title: "Logistica",
    items: [
      { to: "/contrato", label: "Contrato" },
      { to: "/ordem-coleta", label: "Ordem de Coleta" },
      { to: "/agendamentos", label: "Agendamentos" },
      { to: "/analise-fretes", label: "Analise de Fretes" },
    ],
  },
  {
    title: "Financeiro",
    items: [{ to: "/carta-frete", label: "Carta Frete" }],
  },
  {
    title: "Cadastro",
    items: [
      { to: "/buonny", label: "Buonny" },
      { to: "/bsoft", label: "Bsoft TMS" },
    ],
  },
  {
    title: "Clientes",
    items: [{ to: "/clientes", label: "Clientes" }],
  },
];

const ALL_ITEMS = NAV_SECTIONS.flatMap((s) => s.items).concat([
  { to: "/admin", label: "Admin" },
  { to: "/trocar-senha", label: "Trocar Senha" },
]);

function initials(email) {
  if (!email) return "?";
  return email[0].toUpperCase();
}

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const sections = user?.role === "admin"
    ? [...NAV_SECTIONS, { title: "Sistema", items: [{ to: "/admin", label: "Admin" }] }]
    : NAV_SECTIONS;

  const currentLabel = ALL_ITEMS.find((i) => i.to === location.pathname)?.label || "";

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside
        style={{
          width: 232,
          flexShrink: 0,
          background: "var(--panel)",
          border: "1px solid var(--panel-border)",
          borderLeft: "none",
          borderTopRightRadius: 22,
          borderBottomRightRadius: 22,
          padding: 18,
          display: "flex",
          flexDirection: "column",
          gap: 22,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 4px" }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 9,
              background: "linear-gradient(135deg, var(--accent), var(--accent-deep))",
              flexShrink: 0,
            }}
          />
          <div style={{ fontWeight: 700, fontSize: 14.5, letterSpacing: 0.3 }}>ATLANTICO FERTLOG</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18, overflowY: "auto" }}>
          {sections.map((section) => (
            <div key={section.title}>
              <div className="sidebar-caption">{section.title}</div>
              <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) => `sidebar-btn${isActive ? " active" : ""}`}
                  >
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            </div>
          ))}
        </div>

        <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 4px" }}>
            <div className="user-avatar">{initials(user?.email)}</div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {user?.email}
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "capitalize" }}>{user?.role}</div>
            </div>
          </div>
          <NavLink to="/trocar-senha" className={({ isActive }) => `sidebar-btn${isActive ? " active" : ""}`}>
            Trocar senha
          </NavLink>
          <button className="btn-secondary" onClick={logout} style={{ width: "100%" }}>
            Sair
          </button>
        </div>
      </aside>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "14px 16px 16px 14px", minWidth: 0 }}>
        <header
          style={{
            background: "var(--topbar)",
            border: "1px solid var(--topbar-border)",
            borderRadius: 20,
            padding: "14px 20px",
            marginBottom: 16,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            boxShadow: "0 14px 30px -18px rgba(0,0,0,0.6)",
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 700 }}>{currentLabel}</div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>
            Atlantico Fertlog
          </div>
        </header>
        <main style={{ flex: 1, overflowY: "auto" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
