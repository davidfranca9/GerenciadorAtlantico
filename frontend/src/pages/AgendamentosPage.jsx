import { useEffect, useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";
import { formatNome, formatPlaca } from "../utils/format";

const STATUS_OPTIONS = ["Aguardando Agendamento", "Agendado", "Cancelado", "Carregou"];
const ITEM_VAZIO = { pedido: "", cliente: "", produto: "", cidade: "", embalagem: "", toneladas: "" };

export default function AgendamentosPage() {
  const [agendamentos, setAgendamentos] = useState([]);
  const [filtroStatus, setFiltroStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [supplier, setSupplier] = useState("");
  const [loadingDate, setLoadingDate] = useState("");
  const [driverName, setDriverName] = useState("");
  const [plateCavalo, setPlateCavalo] = useState("");
  const [itens, setItens] = useState([{ ...ITEM_VAZIO }]);
  const [error, setError] = useState("");

  async function carregar() {
    setLoading(true);
    try {
      const data = await api.listarAgendamentos(filtroStatus || undefined);
      setAgendamentos(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroStatus]);

  function updateItem(idx, field, value) {
    setItens((prev) => prev.map((it, i) => (i === idx ? { ...it, [field]: value } : it)));
  }

  async function handleCriar(e) {
    e.preventDefault();
    setError("");
    try {
      await api.criarAgendamento({
        supplier,
        loading_date: loadingDate,
        driver_name: driverName,
        plate_cavalo: plateCavalo,
        itens: itens.map((it) => ({ ...it, toneladas: parseFloat(String(it.toneladas).replace(",", ".")) || 0 })),
      });
      setShowForm(false);
      setSupplier("");
      setLoadingDate("");
      setDriverName("");
      setPlateCavalo("");
      setItens([{ ...ITEM_VAZIO }]);
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleStatus(id, status) {
    try {
      await api.atualizarStatusAgendamento(id, status);
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancelar" : "+ Novo Agendamento"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCriar} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="field-grid">
            <div className="field">
              <label>Fornecedor</label>
              <input value={supplier} onChange={(e) => setSupplier(e.target.value)} required />
            </div>
            <DateField label="Data de Carregamento" value={loadingDate} onChange={setLoadingDate} />
            <div className="field">
              <label>Motorista</label>
              <input value={driverName} onChange={(e) => setDriverName(formatNome(e.target.value))} />
            </div>
            <div className="field">
              <label>Placa Cavalo</label>
              <input value={plateCavalo} onChange={(e) => setPlateCavalo(formatPlaca(e.target.value))} placeholder="ABC-1D23" />
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Pedido</th>
                <th>Cliente</th>
                <th>Produto</th>
                <th>Cidade/UF</th>
                <th>Toneladas</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((it, idx) => (
                <tr key={idx}>
                  <td><input value={it.pedido} onChange={(e) => updateItem(idx, "pedido", e.target.value)} /></td>
                  <td><input value={it.cliente} onChange={(e) => updateItem(idx, "cliente", e.target.value)} /></td>
                  <td><input value={it.produto} onChange={(e) => updateItem(idx, "produto", e.target.value)} /></td>
                  <td><input value={it.cidade} onChange={(e) => updateItem(idx, "cidade", e.target.value)} /></td>
                  <td><input value={it.toneladas} onChange={(e) => updateItem(idx, "toneladas", e.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="btn-secondary" onClick={() => setItens((prev) => [...prev, { ...ITEM_VAZIO }])}>
            + Item
          </button>
          <button type="submit" className="btn-primary">Salvar Agendamento</button>
        </form>
      )}

      <div className="field" style={{ maxWidth: 260 }}>
        <label>Filtrar por status</label>
        <select value={filtroStatus} onChange={(e) => setFiltroStatus(e.target.value)}>
          <option value="">Todos</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Fornecedor</th>
              <th>Data</th>
              <th>Motorista</th>
              <th>Itens</th>
              <th>Toneladas</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {agendamentos.map((a) => (
              <tr key={a.id}>
                <td>{a.supplier}</td>
                <td>{a.loading_date}</td>
                <td>{a.driver_name}</td>
                <td>{a.total_items}</td>
                <td>{a.total_tons}</td>
                <td>
                  <select value={a.status} onChange={(e) => handleStatus(a.id, e.target.value)}>
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
            {!loading && agendamentos.length === 0 && (
              <tr>
                <td colSpan={6} style={{ color: "var(--muted)" }}>Nenhum agendamento encontrado.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
