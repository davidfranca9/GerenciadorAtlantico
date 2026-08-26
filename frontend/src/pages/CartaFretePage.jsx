import { useEffect, useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";
import { formatCPF, formatMoney, formatNome, formatPlaca } from "../utils/format";

function hoje() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

function paraDataUTC(iso) {
  const temFuso = /Z$|[+-]\d\d:\d\d$/.test(iso);
  return new Date(temFuso ? iso : `${iso}Z`);
}

function formatarEnvio(iso) {
  if (!iso) return "";
  const dataObj = paraDataUTC(iso);
  if (Number.isNaN(dataObj.getTime())) return iso;
  return dataObj.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
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
  const [enviadas, setEnviadas] = useState([]);
  const [carregandoLista, setCarregandoLista] = useState(true);

  async function carregarEnviadas() {
    try {
      const dadosLista = await api.listarCartasFrete();
      setEnviadas(dadosLista);
    } catch {
      // painel e so consulta - falha aqui nao deve travar a tela de envio
    } finally {
      setCarregandoLista(false);
    }
  }

  useEffect(() => {
    carregarEnviadas();
  }, []);

  async function handleEnviar() {
    setStatus("");
    setLoading(true);
    try {
      await api.enviarCartaFreteEmail({
        DATA: data,
        CONDUTOR: condutor,
        CPF: cpf,
        PLACA_CAVALO: placaCavalo,
        VALOR_FRETE: valorFrete,
        AUTORIZACAO_NUM: autorizacaoNum,
      });
      setStatus("E-mail enviado com sucesso.");
      carregarEnviadas();
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
          <input placeholder="1.500,00" value={valorFrete} onChange={(e) => setValorFrete(formatMoney(e.target.value))} />
        </div>
        <div className="field">
          <label>Número da autorização</label>
          <input value={autorizacaoNum} onChange={(e) => setAutorizacaoNum(e.target.value)} />
        </div>
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <button className="btn-primary" disabled={loading} onClick={handleEnviar}>
          {loading ? "Enviando..." : "Enviar por e-mail"}
        </button>
        {status && <span style={{ fontSize: 13, color: status.startsWith("Erro") ? "var(--danger)" : "var(--success)" }}>{status}</span>}
      </div>

      <div className="card">
        <h2 style={{ margin: "0 0 14px" }}>Cartas Frete Enviadas</h2>
        {carregandoLista ? (
          <div className="inline-alert info"><span className="status-dot" />Carregando...</div>
        ) : enviadas.length === 0 ? (
          <div className="inline-alert warning">Nenhuma carta frete enviada ainda.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Data</th>
                <th>Condutor</th>
                <th>Placa</th>
                <th>Valor</th>
                <th>Nº Autorização</th>
                <th>Enviado em</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {enviadas.map((c) => (
                <tr key={c.id}>
                  <td>{c.data}</td>
                  <td>{c.condutor}</td>
                  <td>{c.placa_cavalo}</td>
                  <td>{c.valor_frete}</td>
                  <td>{c.autorizacao_num}</td>
                  <td>{formatarEnvio(c.created_at)}</td>
                  <td>{c.status === "erro" ? <span style={{ color: "var(--danger)" }}>Falhou</span> : "Enviada"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
