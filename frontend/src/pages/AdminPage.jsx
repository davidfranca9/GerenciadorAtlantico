import { Fragment, useEffect, useState } from "react";
import * as api from "../api/client";

// Permissao por tela, usuario por usuario. A lista de abas vem do backend
// (mesma lista que recusa as rotas com 403), agrupada como a barra lateral:
// aba nova aparece aqui sozinha, e nasce desmarcada pra todo mundo.
export default function AdminPage() {
  const [usuarios, setUsuarios] = useState([]);
  const [grupos, setGrupos] = useState([]);
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [papel, setPapel] = useState("user");
  const [error, setError] = useState("");
  const [permissoesAbertoId, setPermissoesAbertoId] = useState(null);
  const [salvando, setSalvando] = useState(false);

  async function carregar() {
    try {
      setUsuarios(await api.adminListarUsuarios());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    carregar();
    api.adminTelas().then((dados) => setGrupos(dados.grupos || [])).catch((err) => setError(err.message));
  }, []);

  async function handleCriar(e) {
    e.preventDefault();
    setError("");
    try {
      const criado = await api.adminCriarUsuario({ email, name: nome, password: senha, role: papel });
      setEmail("");
      setNome("");
      setSenha("");
      setPapel("user");
      await carregar();
      // Usuario novo nasce sem nenhuma aba: abre as permissoes na hora, senao
      // ele entra no sistema e nao ve nada sem ninguem entender por que.
      if (criado?.role !== "admin") setPermissoesAbertoId(criado.id);
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

  function liberadasDe(u) {
    return (u.paginas_liberadas || "").split(",").filter(Boolean);
  }

  // Marcaveis: Administracao e Configuracoes sao so de administrador e a
  // Seguranca e de todo mundo, entao nao entram na marcacao.
  function marcaveis(grupo) {
    return (grupo.telas || []).filter((t) => !t.somente_admin && !t.sempre_liberada);
  }

  async function salvarTelas(u, rotas) {
    setError("");
    setSalvando(true);
    try {
      await api.adminAtualizarUsuario(u.id, { paginas_liberadas: rotas.join(",") });
      await carregar();
    } catch (err) {
      setError(err.message);
    } finally {
      setSalvando(false);
    }
  }

  function toggleTela(u, rota) {
    const atuais = liberadasDe(u);
    salvarTelas(u, atuais.includes(rota) ? atuais.filter((r) => r !== rota) : [...atuais, rota]);
  }

  // Grupo inteiro em um clique: se ja esta todo marcado, desmarca tudo.
  function toggleGrupo(u, grupo) {
    const atuais = liberadasDe(u);
    const rotas = marcaveis(grupo).map((t) => t.rota);
    const todasMarcadas = rotas.length > 0 && rotas.every((r) => atuais.includes(r));
    salvarTelas(u, todasMarcadas ? atuais.filter((r) => !rotas.includes(r)) : [...new Set([...atuais, ...rotas])]);
  }

  function resumoPermissao(u) {
    if (u.role === "admin") return "Todas as telas";
    const quantas = liberadasDe(u).length;
    if (!quantas) return "Nenhuma aba liberada";
    return `${quantas} aba${quantas === 1 ? "" : "s"}`;
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
              <th>Telas</th>
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
                  <td style={{ whiteSpace: "nowrap" }}>{resumoPermissao(u)}</td>
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
                    <td colSpan={6}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "10px 0" }}>
                        <div>
                          <strong>Telas que {u.name || u.email} pode ver</strong>
                          <div style={{ fontSize: 12, color: "var(--muted)" }}>
                            Marcar uma aba dá acesso de visualização. Lançar, pagar, excluir e importar continuam só para
                            administrador{salvando ? " · salvando..." : ""}
                          </div>
                        </div>
                        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))" }}>
                          {grupos.map((grupo) => {
                            const atuais = liberadasDe(u);
                            const rotas = marcaveis(grupo).map((t) => t.rota);
                            const todas = rotas.length > 0 && rotas.every((r) => atuais.includes(r));
                            return (
                              <section key={grupo.titulo} style={{ border: "1px solid var(--border)", borderRadius: 10, padding: 12 }}>
                                <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
                                  <strong style={{ fontSize: 13 }}>{grupo.titulo}</strong>
                                  {rotas.length > 0 && (
                                    <button
                                      type="button" className="btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }}
                                      disabled={salvando} onClick={() => toggleGrupo(u, grupo)}
                                    >
                                      {todas ? "Desmarcar grupo" : "Marcar grupo"}
                                    </button>
                                  )}
                                </header>
                                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                  {(grupo.telas || []).map((tela) => {
                                    const fixa = tela.somente_admin || tela.sempre_liberada;
                                    return (
                                      <label
                                        key={tela.rota}
                                        title={tela.somente_admin ? "Só administrador" : tela.sempre_liberada ? "Todos os usuários veem" : tela.rota}
                                        style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, opacity: fixa ? 0.55 : 1 }}
                                      >
                                        <input
                                          type="checkbox" disabled={fixa || salvando}
                                          checked={tela.sempre_liberada || atuais.includes(tela.rota)}
                                          onChange={() => toggleTela(u, tela.rota)}
                                        />
                                        {tela.nome}
                                        {tela.somente_admin && <span style={{ fontSize: 11, color: "var(--muted)" }}>(só admin)</span>}
                                      </label>
                                    );
                                  })}
                                </div>
                              </section>
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
