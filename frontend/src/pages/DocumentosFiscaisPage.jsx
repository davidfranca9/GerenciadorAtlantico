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

const EMBALAGENS = ["GRANEL", "BIG BAG", "SACARIA"];

function ListaPendencias({ itens }) {
  if (!itens?.length) return <div className="inline-alert info">Tudo conferido. Pode gerar o rascunho.</div>;
  return (
    <div className="inline-alert warning">
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <strong>Falta resolver antes de emitir:</strong>
        {itens.map((p, i) => <span key={i}>• {p}</span>)}
      </div>
    </div>
  );
}

function LinhaEspelho({ rotulo, valor }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: "var(--muted)", fontSize: 12.5 }}>{rotulo}</span>
      <strong style={{ fontSize: 12.5, textAlign: "right" }}>{valor || "—"}</strong>
    </div>
  );
}

function EmitirCte() {
  const [aberto, setAberto] = useState(false);
  const [agendamentos, setAgendamentos] = useState([]);
  const [agendamentoId, setAgendamentoId] = useState("");
  const [arquivo, setArquivo] = useState(null);
  const [tarifa, setTarifa] = useState("");
  const [aliquota, setAliquota] = useState("12");
  const [embalagem, setEmbalagem] = useState("BIG BAG");
  const [espelho, setEspelho] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!aberto || agendamentos.length) return;
    api.listarAgendamentos().then(setAgendamentos).catch(() => {});
  }, [aberto, agendamentos.length]);

  const campos = () => ({
    agendamento_id: agendamentoId,
    tarifa_por_tonelada: String(tarifa).replace(",", "."),
    aliquota_icms: String(aliquota).replace(",", "."),
    embalagem,
  });

  async function handleConferir() {
    if (!arquivo) {
      setErro("Envie o XML da NF-e primeiro.");
      return;
    }
    setOcupado(true);
    setErro("");
    setEspelho(null);
    setResultado(null);
    try {
      setEspelho(await api.fiscalEspelho(arquivo, { ...campos(), buscar_partes: true }));
    } catch (err) {
      setErro(err.message);
    } finally {
      setOcupado(false);
    }
  }

  async function handleGerarRascunho() {
    setOcupado(true);
    setErro("");
    setResultado(null);
    try {
      setResultado(await api.fiscalEmitirConhecimento(arquivo, campos()));
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
          <strong style={{ fontSize: 15 }}>Gerar CT-e a partir da NF-e</strong>
          <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 4 }}>
            Confira o espelho contra a tela do Bsoft antes de gerar. O envio sai sempre como rascunho.
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
                    #{a.id} · {a.data_agendada || a.loading_date} · {a.driver_name || "sem motorista"} · {a.plate_cavalo}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Tarifa por tonelada</label>
              <input value={tarifa} onChange={(e) => setTarifa(e.target.value)} placeholder="300,00" />
            </div>
            <div className="field">
              <label>Alíquota de ICMS (%)</label>
              <input value={aliquota} onChange={(e) => setAliquota(e.target.value)} placeholder="12" />
            </div>
            <div className="field">
              <label>Embalagem</label>
              <select value={embalagem} onChange={(e) => setEmbalagem(e.target.value)}>
                {EMBALAGENS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <label className="btn-secondary" style={{ cursor: "pointer" }}>
              {arquivo ? "XML: " + arquivo.name : "Enviar XML da NF-e"}
              <input
                type="file"
                accept=".xml"
                onChange={(e) => {
                  setArquivo(e.target.files?.[0] || null);
                  setEspelho(null);
                }}
                style={{ display: "none" }}
              />
            </label>
            <button className="btn-primary" disabled={ocupado || !agendamentoId || !arquivo || !tarifa} onClick={handleConferir}>
              {ocupado ? "Processando..." : "Conferir espelho"}
            </button>
            {espelho && !espelho.pendencias?.length && (
              <button className="btn-primary" disabled={ocupado} onClick={handleGerarRascunho}>
                Gerar rascunho no Bsoft
              </button>
            )}
          </div>

          {erro && <div className="inline-alert warning">{erro}</div>}

          {resultado && (
            <div className="inline-alert info">
              Rascunho criado (operação #{resultado.operacao?.id}, CT-e {resultado.operacao?.cod_conhecimento_bsoft || "—"}).
              Confira na tela do Bsoft antes de autorizar.
            </div>
          )}

          {espelho && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <ListaPendencias itens={espelho.pendencias} />
              <div>
                <strong style={{ fontSize: 13 }}>Como o CT-e vai sair</strong>
                <div style={{ marginTop: 8 }}>
                  <LinhaEspelho rotulo="Remetente" valor={espelho.remetente_nome} />
                  <LinhaEspelho rotulo="Destinatário" valor={espelho.destinatario_nome} />
                  <LinhaEspelho rotulo="Tomador" valor={espelho.tomador} />
                  <LinhaEspelho rotulo="Origem" valor={espelho.municipio_origem + " - " + espelho.uf_origem} />
                  <LinhaEspelho rotulo="Destino" valor={espelho.municipio_destino + " - " + espelho.uf_destino} />
                  <LinhaEspelho rotulo="CFOP" valor={espelho.cfop} />
                  <LinhaEspelho rotulo="Produto" valor={espelho.produto_predominante} />
                  <LinhaEspelho rotulo="Espécie" valor={espelho.especie?.nome} />
                  <LinhaEspelho rotulo="Peso" valor={espelho.peso_kg + " kg"} />
                  <LinhaEspelho rotulo="Volumes" valor={espelho.quantidade} />
                  <LinhaEspelho rotulo="Valor da mercadoria" valor={formatarValor(espelho.valor_mercadoria)} />
                  <LinhaEspelho rotulo="Frete" valor={formatarValor(espelho.valor_frete)} />
                  <LinhaEspelho rotulo="ICMS" valor={formatarValor(espelho.payload?.valorICMS)} />
                </div>
              </div>
              {espelho.payload && (
                <details>
                  <summary style={{ cursor: "pointer", fontSize: 12.5, color: "var(--muted)" }}>
                    Ver o que será enviado ({espelho.endpoint})
                  </summary>
                  <pre className="card" style={{ fontSize: 11.5, marginTop: 8, overflow: "auto", maxHeight: 320 }}>
                    {JSON.stringify(espelho.payload, null, 2)}
                  </pre>
                </details>
              )}
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
