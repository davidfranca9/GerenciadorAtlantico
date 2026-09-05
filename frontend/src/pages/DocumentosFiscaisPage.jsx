import { useEffect, useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";

const PERIODOS = [
  { dias: 7, label: "7 dias" },
  { dias: 30, label: "30 dias" },
  { dias: 90, label: "90 dias" },
];

function formatarValor(valor) {
  const num = Number(valor);
  if (!Number.isFinite(num)) return "-";
  return num.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatarDataHora(texto) {
  if (!texto) return "-";
  const [data, hora] = String(texto).split(" ");
  const partes = (data || "").split("-");
  if (partes.length !== 3) return texto;
  return `${partes[2]}/${partes[1]}/${partes[0]}${hora ? ` ${hora.slice(0, 5)}` : ""}`;
}

function EmitirCte() {
  const [aberto, setAberto] = useState(false);
  const [agendamentos, setAgendamentos] = useState([]);
  const [agendamentoId, setAgendamentoId] = useState("");
  const [chaveNfe, setChaveNfe] = useState("");
  const [valorFrete, setValorFrete] = useState("");
  const [parametro, setParametro] = useState("");
  const [simulacao, setSimulacao] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!aberto || agendamentos.length) return;
    api.listarAgendamentos().then(setAgendamentos).catch(() => {});
  }, [aberto, agendamentos.length]);

  async function handleSimular() {
    setOcupado(true);
    setErro("");
    setSimulacao(null);
    try {
      setSimulacao(await api.fiscalSimular({
        agendamento_id: Number(agendamentoId),
        chave_nfe: chaveNfe,
        valor_frete: parseFloat(String(valorFrete).replace(",", ".")) || 0,
        parametro_criacao_cte: parametro,
      }));
    } catch (err) {
      setErro(err.message);
    } finally {
      setOcupado(false);
    }
  }

  async function handleImportarXml(e) {
    const arquivo = e.target.files?.[0];
    e.target.value = "";
    if (!arquivo || !agendamentoId) {
      setErro("Selecione o agendamento antes de enviar o XML.");
      return;
    }
    setOcupado(true);
    setErro("");
    try {
      const resultado = await api.fiscalImportarNfe(Number(agendamentoId), arquivo);
      if (resultado.nfe?.chave) setChaveNfe(resultado.nfe.chave);
      if (resultado.aviso) setErro(resultado.aviso);
    } catch (err) {
      setErro(err.message);
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 15 }}>Emitir CT-e a partir de um agendamento</strong>
          <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 4 }}>
            Monta a operação e mostra exatamente o que seria enviado ao Bsoft.
          </div>
        </div>
        <button className="btn-secondary" onClick={() => setAberto((v) => !v)}>
          {aberto ? "Fechar" : "Abrir"}
        </button>
      </div>

      {aberto && (
        <>
          <div className="field-grid">
            <div className="field">
              <label>Agendamento</label>
              <select value={agendamentoId} onChange={(e) => setAgendamentoId(e.target.value)}>
                <option value="">Selecione</option>
                {agendamentos.map((a) => (
                  <option key={a.id} value={a.id}>
                    #{a.id} · {a.loading_date} · {a.driver_name || "sem motorista"} · {a.plate_cavalo}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Valor do frete</label>
              <input value={valorFrete} onChange={(e) => setValorFrete(e.target.value)} placeholder="5550,00" />
            </div>
            <div className="field">
              <label>Parâmetro de criação de CT-e</label>
              <input value={parametro} onChange={(e) => setParametro(e.target.value)} placeholder="ainda não configurado" />
            </div>
          </div>

          <div className="field">
            <label>Chave da NF-e (44 dígitos)</label>
            <input value={chaveNfe} onChange={(e) => setChaveNfe(e.target.value)} placeholder="ou envie o XML abaixo" />
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <label className="btn-secondary" style={{ cursor: "pointer" }}>
              Enviar XML da NF-e
              <input type="file" accept=".xml" onChange={handleImportarXml} disabled={ocupado} style={{ display: "none" }} />
            </label>
            <button className="btn-primary" disabled={ocupado || !agendamentoId} onClick={handleSimular}>
              {ocupado ? "Processando..." : "Simular emissão"}
            </button>
          </div>

          {erro && <div className="inline-alert warning">{erro}</div>}

          {simulacao && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {simulacao.pendencias.length > 0 ? (
                <div className="inline-alert warning">
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <strong>Falta para poder emitir:</strong>
                    {simulacao.pendencias.map((p, i) => <span key={i}>• {p}</span>)}
                  </div>
                </div>
              ) : (
                <div className="inline-alert info">Tudo pronto para emitir.</div>
              )}
              <div>
                <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>
                  {simulacao.endpoint}
                </div>
                <pre className="card" style={{ fontSize: 11.5, margin: 0, overflow: "auto", maxHeight: 320 }}>
                  {JSON.stringify(simulacao.payload, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function DocumentosFiscaisPage() {
  const [dias, setDias] = useState(30);
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");

  async function carregar(periodo) {
    setCarregando(true);
    setErro("");
    try {
      setDados(await api.bsoftDocumentosFiscais(periodo));
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    carregar(dias);
  }, [dias]);

  const documentos = dados?.documentos || [];
  const termo = busca.trim().toLowerCase();
  const filtrados = termo
    ? documentos.filter((d) =>
        [d.cte_numero, d.destinatario, d.cliente, d.motorista, d.veiculo, d.ciot, d.chave_acesso]
          .some((campo) => String(campo || "").toLowerCase().includes(termo))
      )
    : documentos;

  const semCiot = documentos.filter((d) => !d.ciot).length;

  return (
    <div className="ops-page">
      <div className="dashboard-header">
        <div>
          <h2>Documentos fiscais emitidos</h2>
          <p>CT-e e contrato de frete (com CIOT) vindos do Bsoft — somente leitura.</p>
        </div>
      </div>

      <EmitirCte />

      <div className="card" style={{ display: "flex", gap: 14, alignItems: "end", flexWrap: "wrap" }}>
        <div className="field" style={{ maxWidth: 200 }}>
          <label>Período</label>
          <select value={dias} onChange={(e) => setDias(Number(e.target.value))}>
            {PERIODOS.map((p) => (
              <option key={p.dias} value={p.dias}>Últimos {p.label}</option>
            ))}
          </select>
        </div>
        <div className="field pedidos-busca-field">
          <label>Buscar</label>
          <div className="pedidos-busca-wrap">
            <Icon name="search" size={15} />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="CT-e, cliente, motorista, placa, CIOT ou chave"
            />
          </div>
        </div>
        <button className="btn-secondary" disabled={carregando} onClick={() => carregar(dias)}>
          {carregando ? "Consultando..." : "Atualizar"}
        </button>
      </div>

      {erro && <div className="inline-alert error">{erro}</div>}
      {dados?.erros && Object.entries(dados.erros).map(([chave, msg]) => (
        <div className="inline-alert warning" key={chave}>Falha ao ler {chave}: {msg}</div>
      ))}

      {!carregando && documentos.length > 0 && semCiot > 0 && (
        <div className="inline-alert warning">
          <Icon name="shield" size={14} />
          {semCiot} CT-e sem contrato de frete/CIOT vinculado no período.
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {carregando ? (
          <div className="inline-alert info" style={{ margin: 16 }}><span className="status-dot" />Carregando...</div>
        ) : filtrados.length === 0 ? (
          <div className="inline-alert warning" style={{ margin: 16 }}>Nenhum documento no período.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>CT-e</th>
                  <th>Emissão</th>
                  <th>Destinatário</th>
                  <th>Motorista</th>
                  <th>Placa</th>
                  <th>Valor</th>
                  <th>CIOT</th>
                  <th>Agendamento</th>
                  <th>Chave de acesso</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((d) => (
                  <tr key={d.cte_id}>
                    <td><strong>{d.cte_numero}</strong></td>
                    <td>{formatarDataHora(d.emitido_em)}</td>
                    <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.destinatario}>
                      {d.destinatario || d.cliente || "-"}
                    </td>
                    <td style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.motorista}>
                      {d.motorista || "-"}
                    </td>
                    <td>{d.veiculo || "-"}{d.carreta ? ` / ${d.carreta}` : ""}</td>
                    <td>{formatarValor(d.valor)}</td>
                    <td>
                      {d.ciot
                        ? <span title={`Operadora: ${d.operadora || "-"} · Contrato ${d.contrato_numero || "-"}`}>{d.ciot}</span>
                        : <span style={{ color: "var(--warning)" }}>sem CIOT</span>}
                    </td>
                    <td>
                      {d.agendamento_id
                        ? <span title={d.agendamento_status || ""}>#{d.agendamento_id}</span>
                        : <span style={{ color: "var(--muted-soft)" }}>—</span>}
                    </td>
                    <td style={{ fontSize: 10.5, fontFamily: "monospace" }}>{d.chave_acesso || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
