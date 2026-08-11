import { useState } from "react";
import * as api from "../api/client";
import { formatCPF, formatDateInput } from "../utils/format";

export default function CartaFretePage() {
  const [data, setData] = useState("");
  const [condutor, setCondutor] = useState("");
  const [cpf, setCpf] = useState("");
  const [placaCavalo, setPlacaCavalo] = useState("");
  const [valorFrete, setValorFrete] = useState("");
  const [autorizacaoNum, setAutorizacaoNum] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleGerar(formato) {
    setStatus("");
    setLoading(true);
    try {
      await api.gerarCartaFrete({
        DATA: data,
        CONDUTOR: condutor,
        CPF: cpf,
        PLACA_CAVALO: placaCavalo,
        VALOR_FRETE: valorFrete,
        AUTORIZACAO_NUM: autorizacaoNum,
        formato,
      });
      setStatus("Documento gerado com sucesso.");
    } catch (err) {
      setStatus(`Erro: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="card field-grid">
        <div className="field">
          <label>Data</label>
          <input placeholder="dd/mm/aaaa" value={data} onChange={(e) => setData(formatDateInput(e.target.value))} />
        </div>
        <div className="field">
          <label>Condutor</label>
          <input value={condutor} onChange={(e) => setCondutor(e.target.value)} />
        </div>
        <div className="field">
          <label>CPF</label>
          <input value={cpf} onChange={(e) => setCpf(formatCPF(e.target.value))} placeholder="000.000.000-00" maxLength={14} />
        </div>
        <div className="field">
          <label>Placa Cavalo</label>
          <input value={placaCavalo} onChange={(e) => setPlacaCavalo(e.target.value)} />
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
        <button className="btn-primary" disabled={loading} onClick={() => handleGerar("docx")}>
          Gerar DOCX
        </button>
        <button className="btn-secondary" disabled={loading} onClick={() => handleGerar("pdf")}>
          Gerar PDF
        </button>
        {status && <span style={{ fontSize: 13, color: status.startsWith("Erro") ? "var(--danger)" : "var(--success)" }}>{status}</span>}
      </div>
    </div>
  );
}
