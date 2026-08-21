import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client";

const VAZIO = { nome: "", cnpj_cpf: "", cidade: "", uf: "", contato: "", email: "", telefone: "", observacoes: "" };

export default function ClientesPage() {
  const [clientes, setClientes] = useState([]);
  const [busca, setBusca] = useState("");
  const [form, setForm] = useState(VAZIO);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [cidadesPorUf, setCidadesPorUf] = useState(null);

  async function carregar() {
    try {
      setClientes(await api.listarClientes(busca || undefined));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca]);

  useEffect(() => {
    api.bsoftCidades().then(setCidadesPorUf).catch((err) => setError(err.message));
  }, []);

  const { cidadesOrdenadas, ufPorCidade } = useMemo(() => {
    const mapa = {};
    const nomes = new Set();
    if (cidadesPorUf) {
      for (const [uf, cidades] of Object.entries(cidadesPorUf)) {
        for (const [nome] of cidades) {
          nomes.add(nome);
          mapa[nome] = uf;
        }
      }
    }
    return { cidadesOrdenadas: [...nomes].sort(), ufPorCidade: mapa };
  }, [cidadesPorUf]);

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateCidade(cidade) {
    setForm((prev) => ({ ...prev, cidade, uf: ufPorCidade[cidade] || "" }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      if (editingId) {
        await api.atualizarCliente(editingId, form);
      } else {
        await api.criarCliente(form);
      }
      setForm(VAZIO);
      setEditingId(null);
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  function handleEdit(cliente) {
    setEditingId(cliente.id);
    setForm({
      nome: cliente.nome,
      cnpj_cpf: cliente.cnpj_cpf,
      cidade: cliente.cidade,
      uf: cliente.uf,
      contato: cliente.contato,
      email: cliente.email,
      telefone: cliente.telefone,
      observacoes: cliente.observacoes,
    });
  }

  async function handleRemove(id) {
    if (!confirm("Remover este cliente?")) return;
    try {
      await api.removerCliente(id);
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      <form onSubmit={handleSubmit} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="field-grid">
          <div className="field">
            <label>Nome*</label>
            <input value={form.nome} onChange={(e) => updateField("nome", e.target.value)} required />
          </div>
          <div className="field">
            <label>CNPJ/CPF</label>
            <input value={form.cnpj_cpf} onChange={(e) => updateField("cnpj_cpf", e.target.value)} />
          </div>
          <div className="field">
            <label>Cidade</label>
            <select value={form.cidade} onChange={(e) => updateCidade(e.target.value)}>
              <option value="">Selecione</option>
              {cidadesOrdenadas.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field">
            <label>UF</label>
            <input value={form.uf} maxLength={2} disabled />
          </div>
          <div className="field">
            <label>Contato</label>
            <input value={form.contato} onChange={(e) => updateField("contato", e.target.value)} />
          </div>
          <div className="field">
            <label>Email</label>
            <input value={form.email} onChange={(e) => updateField("email", e.target.value)} />
          </div>
          <div className="field">
            <label>Telefone</label>
            <input value={form.telefone} onChange={(e) => updateField("telefone", e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Observações</label>
          <input value={form.observacoes} onChange={(e) => updateField("observacoes", e.target.value)} />
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button type="submit" className="btn-primary">{editingId ? "Salvar alteracoes" : "Cadastrar Cliente"}</button>
          {editingId && (
            <button type="button" className="btn-secondary" onClick={() => { setEditingId(null); setForm(VAZIO); }}>
              Cancelar edicao
            </button>
          )}
        </div>
      </form>

      <div className="field" style={{ maxWidth: 300 }}>
        <label>Buscar por nome</label>
        <input value={busca} onChange={(e) => setBusca(e.target.value)} />
      </div>

      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Nome</th>
              <th>CNPJ/CPF</th>
              <th>Cidade/UF</th>
              <th>Contato</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {clientes.map((c) => (
              <tr key={c.id}>
                <td>{c.nome}</td>
                <td>{c.cnpj_cpf}</td>
                <td>{c.cidade}{c.uf ? `/${c.uf}` : ""}</td>
                <td>{c.contato}</td>
                <td style={{ display: "flex", gap: 6 }}>
                  <button className="btn-secondary" onClick={() => handleEdit(c)}>Editar</button>
                  <button className="btn-secondary" onClick={() => handleRemove(c.id)}>Remover</button>
                </td>
              </tr>
            ))}
            {clientes.length === 0 && (
              <tr><td colSpan={5} style={{ color: "var(--muted)" }}>Nenhum cliente cadastrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
