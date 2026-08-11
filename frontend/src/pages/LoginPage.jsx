import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/ordem-coleta");
    } catch (err) {
      setError(err.message || "Falha no login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <form onSubmit={handleSubmit} className="card" style={{ width: 360, display: "flex", flexDirection: "column", gap: 18 }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 14,
              background: "linear-gradient(135deg, var(--accent), var(--accent-deep))",
              boxShadow: "0 10px 24px -8px rgba(107,156,73,0.55)",
            }}
          />
          <div style={{ textAlign: "center" }}>
            <div style={{ fontWeight: 700, fontSize: 18, letterSpacing: 0.3 }}>ATLANTICO FERTLOG</div>
            <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 2 }}>Entrar no sistema</div>
          </div>
        </div>
        <div className="field">
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </div>
        <div className="field">
          <label>Senha</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {error && <div style={{ color: "var(--danger)", fontSize: 13 }}>{error}</div>}
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </div>
  );
}
