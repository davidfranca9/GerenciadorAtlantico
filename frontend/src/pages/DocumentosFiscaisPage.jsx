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

// Especies do cadastro do Bsoft, com os ids reais lidos do combo especieId
// da tela de emissao. A ordem e a mesma que aparece la.
const ESPECIES = [
  [1, "GRANEL"], [3, "SACOS"], [4, "FARDOS"], [5, "BIG BAG"], [6, "PALLETS"],
  [7, "CAIXAS"], [8, "SACO DE 50 KG"], [9, "Saco de 20kg"], [10, "BIG BAG 1000 KG"],
  [11, "SACO DE 25 KG"], [12, "SC X 25 KG"], [13, "Tonelada"], [14, "SACOS 50 KG"],
];

function Secao({ titulo, children }) {
  return (
    <fieldset
      style={{
        border: "1px solid var(--border)", borderRadius: 8, padding: "12px 14px 14px",
        margin: 0, display: "flex", flexDirection: "column", gap: 10,
      }}
    >
      <legend style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: "var(--muted)", padding: "0 6px" }}>
        {titulo}
      </legend>
      {children}
    </fieldset>
  );
}

function Campo({ rotulo, valor, largura = 1 }) {
  return (
    <div style={{ flex: largura, minWidth: 120 }}>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>{rotulo}</div>
      <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2, wordBreak: "break-word" }}>{valor || "—"}</div>
    </div>
  );
}

function Linha({ children }) {
  return <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>{children}</div>;
}

function EmitirCte() {
  const [aberto, setAberto] = useState(false);
  const [agendamentos, setAgendamentos] = useState([]);
  const [agendamentoId, setAgendamentoId] = useState("");
  const [arquivo, setArquivo] = useState(null);
  const [tarifa, setTarifa] = useState("");
  const [aliquota, setAliquota] = useState("12");
  const [km, setKm] = useState("");
  const [embalagem, setEmbalagem] = useState("BIG BAG");
  const [especieId, setEspecieId] = useState("");
  const [definitivo, setDefinitivo] = useState(false);
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
    km: String(km).replace(",", "."),
    embalagem,
    especie_id: especieId,
  });

  async function handleConferir() {
    if (!arquivo) {
      setErro("Envie o XML da NF-e primeiro.");
      return;
    }
    setOcupado(true);
    setErro("");
    setResultado(null);
    try {
      const dados = await api.fiscalEspelho(arquivo, { ...campos(), buscar_partes: true });
      setEspelho(dados);
      if (dados.especie?.especie_id && !especieId) setEspecieId(String(dados.especie.especie_id));
    } catch (err) {
      setErro(err.message);
    } finally {
      setOcupado(false);
    }
  }

  async function handleEmitir() {
    setOcupado(true);
    setErro("");
    setResultado(null);
    try {
      setResultado(await api.fiscalEmitirConhecimento(arquivo, {
        ...campos(),
        confirmar_emissao_real: definitivo ? "true" : "",
      }));
    } catch (err) {
      setErro(err.message);
    } finally {
      setOcupado(false);
    }
  }

  const e = espelho || {};
  const p = espelho?.payload || {};
  const merc = p.mercadorias?.[0] || {};
  const pronto = espelho && !espelho.pendencias?.length;

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 15 }}>Emitir CT-e</strong>
          <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 4 }}>
            Mesmas seções da tela do Bsoft, preenchidas a partir da NF-e.
          </div>
        </div>
        <button className="btn-secondary" onClick={() => setAberto((v) => !v)}>
          {aberto ? "Fechar" : "Abrir"}
        </button>
      </div>

      {aberto && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Secao titulo="Dados da emissão">
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
                <label>Km do trecho</label>
                <input value={km} onChange={(e) => setKm(e.target.value)} placeholder="850" />
              </div>
              <div className="field">
                <label>Espécie da carga</label>
                <select value={especieId} onChange={(e) => setEspecieId(e.target.value)}>
                  <option value="">Pela embalagem do pedido</option>
                  {ESPECIES.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Embalagem do pedido</label>
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
                  onChange={(e) => { setArquivo(e.target.files?.[0] || null); setEspelho(null); }}
                  style={{ display: "none" }}
                />
              </label>
              <button className="btn-primary" disabled={ocupado || !agendamentoId || !arquivo || !tarifa || !km} onClick={handleConferir}>
                {ocupado ? "Processando..." : "Conferir"}
              </button>
            </div>
          </Secao>

          {erro && <div className="inline-alert warning">{erro}</div>}

          {resultado && (
            <div className="inline-alert info">
              {resultado.rascunho ? "Rascunho criado" : "CT-e emitido"} — operação #{resultado.operacao?.id},
              {" "}CT-e {resultado.operacao?.cod_conhecimento_bsoft || "—"}. Confira no Bsoft.
            </div>
          )}

          {e.pendencias?.length > 0 && (
                <div className="inline-alert warning">
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <strong>Falta resolver:</strong>
                {e.pendencias.map((item, i) => <span key={i}>• {item}</span>)}
              </div>
            </div>
          )}

              <Secao titulo="Identificação">
                <Linha>
                  <Campo rotulo="Modelo" valor="57" />
                  <Campo rotulo="Série" valor="1" />
                  <Campo rotulo="Tipo do CT-e" valor="Normal" />
                  <Campo rotulo="Tipo do serviço" valor="Normal" />
                  <Campo rotulo="Modal" valor="Rodoviário" />
                  <Campo rotulo="Emissão" valor={p.dtEmissao} />
                </Linha>
              </Secao>

              <Secao titulo="Prestação">
                <Linha>
                  <Campo rotulo="CFOP" valor={e.cfop} largura={2} />
                  <Campo rotulo="Origem" valor={`${e.municipio_origem} - ${e.uf_origem} (${e.ibge_origem})`} largura={3} />
                  <Campo rotulo="Destino" valor={`${e.municipio_destino} - ${e.uf_destino} (${e.ibge_destino})`} largura={3} />
                </Linha>
              </Secao>

              <Secao titulo="Participantes">
                <Linha>
                  <Campo rotulo="Remetente" valor={e.remetente_nome} largura={3} />
                  <Campo rotulo="CNPJ/CPF" valor={e.remetente_doc} />
                  <Campo rotulo="Cadastro" valor={e.partes?.remetente?.pessoa_id} />
                </Linha>
                <Linha>
                  <Campo rotulo="Destinatário" valor={e.destinatario_nome} largura={3} />
                  <Campo rotulo="CNPJ/CPF" valor={e.destinatario_doc} />
                  <Campo rotulo="Cadastro" valor={e.partes?.destinatario?.pessoa_id} />
                </Linha>
                <Linha>
                  <Campo rotulo="Tomador do serviço" valor={e.tomador === "destinatario" ? e.destinatario_nome : e.remetente_nome} largura={3} />
                  <Campo rotulo="Paga o frete" valor={p.pagamentoFrete === "D" ? "Destinatário" : p.pagamentoFrete === "R" ? "Remetente" : "—"} />
                  <Campo rotulo="Km" valor={p.km} />
                </Linha>
              </Secao>

              <Secao titulo="Carga">
                <Linha>
                  <Campo rotulo="Produto predominante" valor={e.produto_predominante} largura={4} />
                  <Campo rotulo="Espécie" valor={e.especie?.nome} largura={2} />
                </Linha>
                <Linha>
                  <Campo rotulo="Peso bruto" valor={`${e.peso_kg} kg`} />
                  <Campo rotulo="Quantidade" valor={e.quantidade} />
                  <Campo rotulo="Valor da mercadoria" valor={formatarValor(e.valor_mercadoria)} />
                  <Campo rotulo="Natureza da carga" valor={merc.naturezaCarga === "4" ? "Fertilizantes" : merc.naturezaCarga} />
                </Linha>
              </Secao>

              <Secao titulo="Documentos originários">
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ textAlign: "left", color: "var(--muted)" }}>
                        <th style={{ padding: "4px 8px 6px 0" }}>NF-e</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>Série</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>Emissão</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>CFOP</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>Valor</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>BC ICMS</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>ICMS</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>BC ST</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>ST</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr style={{ fontVariantNumeric: "tabular-nums" }}>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.notaFiscal}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.serieNotaFiscal}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.dtFiscal}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.nCFOP}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.valor)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vBC)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vICMS)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vBCST)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vST)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--muted)", wordBreak: "break-all" }}>
                  Chave: {merc.chaveNFe}
                </div>
              </Secao>

              <Secao titulo="Valores da prestação">
                <Linha>
                  <Campo rotulo="Tarifa peso" valor={formatarValor(p.tarifaDigitada)} />
                  <Campo rotulo="Frete valor" valor={formatarValor(p.valorFrete)} />
                  <Campo rotulo="Total do serviço" valor={formatarValor(p.totalServico)} />
                  <Campo rotulo="A receber" valor={formatarValor(p.totalPrestacao)} />
                </Linha>
              </Secao>

              <Secao titulo="Imposto">
                <Linha>
                  <Campo rotulo="Situação tributária" valor={p.CST === "000" ? "00 - Tributação normal" : p.CST} largura={2} />
                  <Campo rotulo="Base de cálculo" valor={formatarValor(p.baseCalculo)} />
                  <Campo rotulo="Alíquota" valor={p.aliquota ? `${p.aliquota},00%` : "—"} />
                  <Campo rotulo="Valor do ICMS" valor={formatarValor(p.valorICMS)} />
                </Linha>
              </Secao>

              <Secao titulo="Seguro">
                <Linha>
                  <Campo rotulo="Seguradora" valor="CHUBB SEGUROS BRASIL S.A." largura={3} />
                  <Campo rotulo="Apólice" valor={p.numeroApolice} />
                  <Campo rotulo="Responsável" valor="Emitente" />
                </Linha>
              </Secao>

              <Secao titulo="Veículo e motorista">
                <Linha>
                  <Campo rotulo="Motorista" valor={e.veiculos?.motorista_id ? `cadastro ${e.veiculos.motorista_id}` : "não encontrado"} />
                  <Campo rotulo="Cavalo" valor={e.veiculos?.veiculo_id ? `cadastro ${e.veiculos.veiculo_id}` : "não encontrado"} />
                  <Campo rotulo="Carreta" valor={e.veiculos?.carreta_id ? `cadastro ${e.veiculos.carreta_id}` : "—"} />
                  <Campo rotulo="Segunda carreta" valor={e.veiculos?.semireboque_id ? `cadastro ${e.veiculos.semireboque_id}` : "—"} />
                </Linha>
              </Secao>

              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5 }}>
                  <input type="checkbox" checked={definitivo} onChange={(e) => setDefinitivo(e.target.checked)} />
                  Emitir definitivo (não rascunho)
                </label>
                <button className="btn-primary" disabled={ocupado || !pronto} onClick={handleEmitir}>
                  {definitivo ? "Emitir CT-e no Bsoft" : "Gerar rascunho no Bsoft"}
                </button>
                <details style={{ marginLeft: "auto" }}>
                  <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--muted)" }}>Ver JSON enviado</summary>
                  <pre className="card" style={{ fontSize: 11, marginTop: 8, overflow: "auto", maxHeight: 300 }}>
                    {JSON.stringify(p, null, 2)}
                  </pre>
                </details>
              </div>
        </div>
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
