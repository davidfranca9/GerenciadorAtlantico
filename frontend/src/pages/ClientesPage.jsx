import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client";

const VAZIO = { nome: "", cnpj_cpf: "", cidade: "", uf: "", contato: "", email: "", telefone: "", observacoes: "" };

const CAPITAIS_POR_UF = {
  AC: "Rio Branco", AL: "Maceió", AP: "Macapá", AM: "Manaus", BA: "Salvador", CE: "Fortaleza",
  DF: "Brasília", ES: "Vitória", GO: "Goiânia", MA: "São Luís", MT: "Cuiabá", MS: "Campo Grande",
  MG: "Belo Horizonte", PA: "Belém", PB: "João Pessoa", PR: "Curitiba", PE: "Recife", PI: "Teresina",
  RJ: "Rio de Janeiro", RN: "Natal", RS: "Porto Alegre", RO: "Porto Velho", RR: "Boa Vista",
  SC: "Florianópolis", SP: "São Paulo", SE: "Aracaju", TO: "Palmas",
};

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

  const cidadesDoEstado = useMemo(() => {
    if (!cidadesPorUf || !form.uf) return [];
    const nomes = (cidadesPorUf[form.uf] || []).map(([nome]) => nome);
    const capital = CAPITAIS_POR_UF[form.uf];
    const capitalNorm = (capital || "").toUpperCase();
    const encontrouCapital = nomes.find((n) => n.toUpperCase() === capitalNorm);
    const resto = nomes.filter((n) => n.toUpperCase() !== capitalNorm).sort();
    return encontrouCapital ? [encontrouCapital, ...resto] : resto;
  }, [cidadesPorUf, form.uf]);

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateUf(uf) {
    setForm((prev) => ({ ...prev, uf, cidade: "" }));
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
            <label>UF</label>
            <select value={form.uf} onChange={(e) => updateUf(e.target.value)}>
              <option value="">Selecione</option>
              {cidadesPorUf && Object.keys(cidadesPorUf).sort().map((uf) => <option key={uf} value={uf}>{uf}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Cidade</label>
            <select value={form.cidade} onChange={(e) => updateField("cidade", e.target.value)}>
              <option value="">Selecione</option>
              {cidadesDoEstado.map((c) => (
                <option key={c} value={c}>{c === CAPITAIS_POR_UF[form.uf] ? `★ ${c} (Capital)` : c}</option>
              ))}
            </select>
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
