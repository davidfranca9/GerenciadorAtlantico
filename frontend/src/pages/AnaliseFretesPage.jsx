import { useEffect, useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";

export default function AnaliseFretesPage() {
  const [cotacoes, setCotacoes] = useState([]);
  const [busca, setBusca] = useState("");
  const [dataCotacao, setDataCotacao] = useState("");
  const [destino, setDestino] = useState("");
  const [valorTonelada, setValorTonelada] = useState("");
  const [error, setError] = useState("");

  async function carregar() {
    try {
      const data = await api.listarCotacoes(busca || undefined);
      setCotacoes(data);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca]);

  async function handleCadastrar(e) {
    e.preventDefault();
    setError("");
    try {
      await api.cadastrarCotacao({
        data_cotacao: dataCotacao,
        destino,
        valor_tonelada: parseFloat(String(valorTonelada).replace(",", ".")) || 0,
      });
      setDataCotacao("");
      setDestino("");
      setValorTonelada("");
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      <form onSubmit={handleCadastrar} className="card field-grid" style={{ alignItems: "end" }}>
        <DateField label="Data da Cotação" value={dataCotacao} onChange={setDataCotacao} required />
        <div className="field">
          <label>Destino</label>
          <input value={destino} onChange={(e) => setDestino(e.target.value)} required />
        </div>
        <div className="field">
          <label>Valor por Tonelada (R$)</label>
          <input value={valorTonelada} onChange={(e) => setValorTonelada(e.target.value)} required />
        </div>
        <button type="submit" className="btn-primary">Cadastrar cotação</button>
      </form>

      <div className="field" style={{ maxWidth: 300 }}>
        <label>Buscar por destino</label>
        <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex: Sorocaba" />
      </div>

      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Data</th>
              <th>Destino</th>
              <th>Valor/Tonelada</th>
            </tr>
          </thead>
          <tbody>
            {cotacoes.map((c) => (
              <tr key={c.id}>
                <td>{c.data_cotacao}</td>
                <td>{c.destino}</td>
                <td>R$ {Number(c.valor_tonelada).toFixed(2)}</td>
              </tr>
            ))}
            {cotacoes.length === 0 && (
              <tr>
                <td colSpan={3} style={{ color: "var(--muted)" }}>Nenhuma cotacao encontrada.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
