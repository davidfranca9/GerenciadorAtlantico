import { useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";
import { formatCPF, formatNome, formatPlaca } from "../utils/format";

function hoje() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

export default function CartaFretePage() {
  const [data, setData] = useState(hoje());
  const [condutor, setCondutor] = useState("");
  const [cpf, setCpf] = useState("");
  const [placaCavalo, setPlacaCavalo] = useState("");
  const [valorFrete, setValorFrete] = useState("");
  const [autorizacaoNum, setAutorizacaoNum] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleGerar() {
    setStatus("");
    setLoading(true);
    try {
      const base = {
        DATA: data,
        CONDUTOR: condutor,
        CPF: cpf,
        PLACA_CAVALO: placaCavalo,
        VALOR_FRETE: valorFrete,
        AUTORIZACAO_NUM: autorizacaoNum,
      };
      await api.gerarCartaFrete({ ...base, formato: "docx" });
      await api.gerarCartaFrete({ ...base, formato: "pdf" });
      setStatus("Documentos gerados com sucesso.");
    } catch (err) {
      setStatus(`Erro: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="card field-grid">
        <DateField label="Data" value={data} onChange={setData} />
        <div className="field">
          <label>Condutor</label>
          <input value={condutor} onChange={(e) => setCondutor(formatNome(e.target.value))} />
        </div>
        <div className="field">
          <label>CPF</label>
          <input value={cpf} onChange={(e) => setCpf(formatCPF(e.target.value))} placeholder="000.000.000-00" maxLength={14} />
        </div>
        <div className="field">
          <label>Placa Cavalo</label>
          <input value={placaCavalo} onChange={(e) => setPlacaCavalo(formatPlaca(e.target.value))} placeholder="ABC-1D23" />
        </div>
        <div className="field">
          <label>Valor do Frete</label>
          <input placeholder="1500,00" value={valorFrete} onChange={(e) => setValorFrete(e.target.value)} />
        </div>
        <div className="field">
          <label>Numero da Autorizacao</label>
          <input value={autorizacaoNum} onChange={(e) => setAutorizacaoNum(e.target.value)} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <button className="btn-primary" disabled={loading} onClick={handleGerar}>
          {loading ? "Gerando..." : "Gerar Autorização"}
        </button>
        {status && <span style={{ fontSize: 13, color: status.startsWith("Erro") ? "var(--danger)" : "var(--success)" }}>{status}</span>}
      </div>
    </div>
  );
}
