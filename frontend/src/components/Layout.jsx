import { NavLink, Outlet } from "react-router-dom";
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

export default function Layout() {
  const { user, logout } = useAuth();
  const sections = user?.role === "admin"
    ? [...NAV_SECTIONS, { title: "Sistema", items: [{ to: "/admin", label: "Admin" }] }]
    : NAV_SECTIONS;

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <aside
        style={{
          width: 220,
          background: "var(--frame)",
          borderRight: "1px solid var(--border)",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: 0.5 }}>ATLANTICO FERTLOG</div>
        {sections.map((section) => (
          <div key={section.title}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase" }}>
              {section.title}
            </div>
            <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  style={({ isActive }) => ({
                    padding: "8px 10px",
                    borderRadius: 6,
                    color: isActive ? "#072926" : "var(--text)",
                    background: isActive ? "var(--accent)" : "transparent",
                    textDecoration: "none",
                    fontSize: 14,
                    fontWeight: isActive ? 700 : 400,
                  })}
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        ))}
        <div style={{ marginTop: "auto" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>{user?.email}</div>
          <NavLink to="/trocar-senha" style={{ fontSize: 12, color: "var(--accent)", display: "block", marginBottom: 8 }}>
            Trocar senha
          </NavLink>
          <button className="btn-secondary" onClick={logout} style={{ width: "100%" }}>
            Sair
          </button>
        </div>
      </aside>
      <main style={{ flex: 1, padding: 28, overflowY: "auto" }}>
        <Outlet />
      </main>
    </div>
  );
}
