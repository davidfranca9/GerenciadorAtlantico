import { Fragment, useEffect, useState } from "react";
import * as api from "../api/client";
import { PAGINAS_BLOQUEAVEIS } from "../components/Layout";

export default function AdminPage() {
  const [usuarios, setUsuarios] = useState([]);
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState("user");
  const [error, setError] = useState("");
  const [permissoesAbertoId, setPermissoesAbertoId] = useState(null);

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

  async function toggleAcessoPagina(u, to) {
    const atuais = (u.paginas_bloqueadas || "").split(",").filter(Boolean);
    const novas = atuais.includes(to) ? atuais.filter((p) => p !== to) : [...atuais, to];
    try {
      await api.adminAtualizarUsuario(u.id, { paginas_bloqueadas: novas.join(",") });
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

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
              <Fragment key={u.id}>
                <tr>
                  <td>{u.email}</td>
                  <td>{u.name}</td>
                  <td>{u.role}</td>
                  <td>{u.is_active ? "Sim" : "Não"}</td>
                  <td style={{ display: "flex", gap: 6 }}>
                    <button className="btn-secondary" onClick={() => togglePapel(u)}>
                      {u.role === "admin" ? "Tornar usuario" : "Tornar admin"}
                    </button>
                    <button className="btn-secondary" onClick={() => toggleAtivo(u)}>
                      {u.is_active ? "Desativar" : "Ativar"}
                    </button>
                    {u.role !== "admin" && (
                      <button className="btn-secondary" onClick={() => setPermissoesAbertoId(permissoesAbertoId === u.id ? null : u.id)}>
                        {permissoesAbertoId === u.id ? "Fechar" : "Permissões"}
                      </button>
                    )}
                  </td>
                </tr>
                {permissoesAbertoId === u.id && (
                  <tr>
                    <td colSpan={5}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "10px 0" }}>
                        <strong>Abas visíveis para {u.name || u.email}</strong>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
                          {PAGINAS_BLOQUEAVEIS.map((item) => {
                            const bloqueada = (u.paginas_bloqueadas || "").split(",").filter(Boolean).includes(item.to);
                            return (
                              <label key={item.to} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                                <input type="checkbox" checked={!bloqueada} onChange={() => toggleAcessoPagina(u, item.to)} />
                                {item.label}
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
