import { useEffect, useState } from "react";
import * as api from "../api/client";

export default function AdminPage() {
  const [usuarios, setUsuarios] = useState([]);
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState("user");
  const [error, setError] = useState("");

  async function carregar() {
    try {
      setUsuarios(await api.adminListarUsuarios());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function handleCriar(e) {
    e.preventDefault();
    setError("");
    try {
      await api.adminCriarUsuario({ email, name: nome, password: senha, role: papel });
      setEmail("");
      setNome("");
      setSenha("");
      setPapel("user");
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleAtivo(u) {
    try {
      await api.adminAtualizarUsuario(u.id, { is_active: !u.is_active });
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  async function togglePapel(u) {
    try {
      await api.adminAtualizarUsuario(u.id, { role: u.role === "admin" ? "user" : "admin" });
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <h2 style={{ margin: 0 }}>Administracao de Usuarios</h2>

      <form onSubmit={handleCriar} className="card field-grid" style={{ alignItems: "end" }}>
        <div className="field">
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label>Nome</label>
          <input value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
        <div className="field">
          <label>Senha</label>
          <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} required minLength={8} />
        </div>
        <div className="field">
          <label>Papel</label>
          <select value={papel} onChange={(e) => setPapel(e.target.value)}>
            <option value="user">Usuario</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button type="submit" className="btn-primary">Criar Usuario</button>
      </form>

      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Nome</th>
              <th>Papel</th>
              <th>Ativo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.id}>
                <td>{u.email}</td>
                <td>{u.name}</td>
                <td>{u.role}</td>
                <td>{u.is_active ? "Sim" : "Nao"}</td>
                <td style={{ display: "flex", gap: 6 }}>
                  <button className="btn-secondary" onClick={() => togglePapel(u)}>
                    {u.role === "admin" ? "Tornar usuario" : "Tornar admin"}
                  </button>
                  <button className="btn-secondary" onClick={() => toggleAtivo(u)}>
                    {u.is_active ? "Desativar" : "Ativar"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
