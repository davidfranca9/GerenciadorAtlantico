import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";

export default function LoginPage() {
  const { login } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault(); setError(""); setLoading(true);
    try { await login(email, password); navigate("/ordem-coleta"); }
    catch (err) { setError(err.message || "Falha no login"); }
    finally { setLoading(false); }
  }

  return (
    <div className="login-page">
      <section className="login-panel">
        <div className="login-brand">
          <div className="brand-logo"><img src="/logo.svg" alt="Atlântico Fertlog" /></div>
          <div className="brand-copy"><strong>ATLÂNTICO</strong><span>FERTLOG</span></div>
        </div>
        <button type="button" className="icon-btn login-theme" onClick={toggleTheme} title="Alternar tema"><Icon name={theme === "dark" ? "sun" : "moon"} /></button>
        <div className="login-form-wrap">
          <span className="login-kicker">ACESSO SEGURO</span>
          <h1>Bem-vindo de volta.</h1>
          <p>Entre com suas credenciais para acessar a central de operações.</p>
          <form onSubmit={handleSubmit} className="login-form">
            <div className="field"><label>E-mail corporativo</label><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nome@empresa.com.br" required autoFocus /></div>
            <div className="field"><label>Senha</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Digite sua senha" required /></div>
            {error && <div style={{ color: "var(--danger)", fontSize: 12 }}>{error}</div>}
            <button type="submit" className="btn-primary" disabled={loading}>{loading ? "Autenticando..." : "Entrar no sistema"}</button>
          </form>
        </div>
        <div className="login-footer">© {new Date().getFullYear()} Atlântico Fertlog · Ambiente protegido</div>
      </section>
      <aside className="login-visual">
        <div className="login-visual-content">
          <span className="visual-pill"><span className="status-dot" /> GESTÃO LOGÍSTICA INTEGRADA</span>
          <h2>Operação fluida.<br />Decisões precisas.</h2>
          <p>Contratos, coletas, agendamentos e parceiros conectados em uma única central operacional.</p>
          <div className="visual-stats">
            <div><strong>Centralizado</strong><span>Dados e documentos</span></div>
            <div><strong>Ágil</strong><span>Rotina operacional</span></div>
            <div><strong>Seguro</strong><span>Acesso controlado</span></div>
          </div>
        </div>
      </aside>
    </div>
  );
}
