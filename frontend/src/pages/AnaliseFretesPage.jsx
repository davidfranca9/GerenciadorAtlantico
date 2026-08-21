import { useEffect, useMemo, useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";

const CAPITAIS_POR_UF = {
  AC: "Rio Branco", AL: "Maceió", AP: "Macapá", AM: "Manaus", BA: "Salvador", CE: "Fortaleza",
  DF: "Brasília", ES: "Vitória", GO: "Goiânia", MA: "São Luís", MT: "Cuiabá", MS: "Campo Grande",
  MG: "Belo Horizonte", PA: "Belém", PB: "João Pessoa", PR: "Curitiba", PE: "Recife", PI: "Teresina",
  RJ: "Rio de Janeiro", RN: "Natal", RS: "Porto Alegre", RO: "Porto Velho", RR: "Boa Vista",
  SC: "Florianópolis", SP: "São Paulo", SE: "Aracaju", TO: "Palmas",
};

function montarDestino({ bairro, cidade, uf }) {
  const local = [bairro.trim(), cidade.trim()].filter(Boolean).join(" - ");
  return uf ? `${local}${local ? "/" : ""}${uf}` : local;
}

export default function AnaliseFretesPage() {
  const [cotacoes, setCotacoes] = useState([]);
  const [busca, setBusca] = useState("");
  const [dataCotacao, setDataCotacao] = useState("");
  const [ufDestino, setUfDestino] = useState("");
  const [cidadeDestino, setCidadeDestino] = useState("");
  const [bairroDestino, setBairroDestino] = useState("");
  const [valorTonelada, setValorTonelada] = useState("");
  const [clienteId, setClienteId] = useState("");
  const [observacoes, setObservacoes] = useState("");
  const [error, setError] = useState("");
  const [cidadesPorUf, setCidadesPorUf] = useState(null);
  const [clientes, setClientes] = useState([]);

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

  useEffect(() => {
    api.bsoftCidades().then(setCidadesPorUf).catch((err) => setError(err.message));
    api.listarClientes().then(setClientes).catch((err) => setError(err.message));
  }, []);

  const cidadesDoEstado = useMemo(() => {
    if (!cidadesPorUf || !ufDestino) return [];
    const nomes = (cidadesPorUf[ufDestino] || []).map(([nome]) => nome);
    const capital = CAPITAIS_POR_UF[ufDestino];
    const capitalNorm = (capital || "").toUpperCase();
    const encontrouCapital = nomes.find((n) => n.toUpperCase() === capitalNorm);
    const resto = nomes.filter((n) => n.toUpperCase() !== capitalNorm).sort();
    return encontrouCapital ? [encontrouCapital, ...resto] : resto;
  }, [cidadesPorUf, ufDestino]);

  async function handleCadastrar(e) {
    e.preventDefault();
    setError("");
    try {
      const clienteSelecionado = clientes.find((c) => String(c.id) === clienteId);
      await api.cadastrarCotacao({
        data_cotacao: dataCotacao,
        destino: montarDestino({ bairro: bairroDestino, cidade: cidadeDestino, uf: ufDestino }),
        valor_tonelada: parseFloat(String(valorTonelada).replace(",", ".")) || 0,
        cliente_id: clienteSelecionado ? clienteSelecionado.id : null,
        cliente_nome: clienteSelecionado ? clienteSelecionado.nome : "",
        observacoes,
      });
      setDataCotacao("");
      setUfDestino("");
      setCidadeDestino("");
      setBairroDestino("");
      setValorTonelada("");
      setClienteId("");
      setObservacoes("");
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
          <label>Cliente</label>
          <select value={clienteId} onChange={(e) => setClienteId(e.target.value)}>
            <option value="">Selecione</option>
            {clientes.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select>
        </div>
        <div className="field">
          <label>UF</label>
          <select value={ufDestino} onChange={(e) => { setUfDestino(e.target.value); setCidadeDestino(""); }}>
            <option value="">Selecione</option>
            {cidadesPorUf && Object.keys(cidadesPorUf).sort().map((uf) => <option key={uf} value={uf}>{uf}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Cidade</label>
          <select value={cidadeDestino} onChange={(e) => setCidadeDestino(e.target.value)}>
            <option value="">Selecione</option>
            {cidadesDoEstado.map((c) => (
              <option key={c} value={c}>{c === CAPITAIS_POR_UF[ufDestino] ? `★ ${c} (Capital)` : c}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Bairro</label>
          <input value={bairroDestino} onChange={(e) => setBairroDestino(e.target.value)} placeholder="Opcional" />
        </div>
        <div className="field">
          <label>Valor por Tonelada (R$)</label>
          <input value={valorTonelada} onChange={(e) => setValorTonelada(e.target.value)} required />
        </div>
        <div className="field field-full">
          <label>Observações</label>
          <textarea value={observacoes} onChange={(e) => setObservacoes(e.target.value)} rows={2} placeholder="Observações sobre a cotação" />
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
              <th>Cliente</th>
              <th>Destino</th>
              <th>Valor/Tonelada</th>
              <th>Observações</th>
            </tr>
          </thead>
          <tbody>
            {cotacoes.map((c) => (
              <tr key={c.id}>
                <td>{c.data_cotacao}</td>
                <td>{c.cliente_nome || "-"}</td>
                <td>{c.destino}</td>
                <td>R$ {Number(c.valor_tonelada).toFixed(2)}</td>
                <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.observacoes}>{c.observacoes || "-"}</td>
              </tr>
            ))}
            {cotacoes.length === 0 && (
              <tr>
                <td colSpan={5} style={{ color: "var(--muted)" }}>Nenhuma cotacao encontrada.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
