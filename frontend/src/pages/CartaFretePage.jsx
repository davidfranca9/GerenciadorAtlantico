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

// Valor do <input type="datetime-local">: horario local, sem fuso.
function paraCampoLocal(data) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${data.getFullYear()}-${pad(data.getMonth() + 1)}-${pad(data.getDate())}T${pad(data.getHours())}:${pad(data.getMinutes())}`;
}

const SITUACAO = {
  agendada: ["Agendada", "var(--accent)"],
  enviando: ["Enviando", "var(--muted)"],
  enviada: ["Enviada", "var(--success)"],
  erro: ["Falhou", "var(--danger)"],
  cancelada: ["Cancelada", "var(--muted)"],
};

export default function CartaFretePage() {
  const [data, setData] = useState(hoje());
  const [condutor, setCondutor] = useState("");
  const [cpf, setCpf] = useState("");
  const [placaCavalo, setPlacaCavalo] = useState("");
  const [valorFrete, setValorFrete] = useState("");
  const [autorizacaoNum, setAutorizacaoNum] = useState("");
  const [enviarEm, setEnviarEm] = useState("");
  const [status, setStatus] = useState("");
  const [acao, setAcao] = useState(""); // "email" | "pdf" | "docx" | "agendar" | "cancelar"
  const [enviadas, setEnviadas] = useState([]);
  const [carregandoLista, setCarregandoLista] = useState(true);

  async function carregarEnviadas() {
    try {
      setEnviadas(await api.listarCartasFrete());
    } catch {
      // painel e so consulta - falha aqui nao deve travar a tela de envio
    } finally {
      setCarregandoLista(false);
    }
  }

  // A lista se atualiza sozinha: e assim que uma carta agendada aparece
  // como "Enviada" quando chega a hora, sem precisar recarregar a pagina.
  useEffect(() => {
    carregarEnviadas();
    const timer = setInterval(carregarEnviadas, 60000);
    return () => clearInterval(timer);
  }, []);

  function dados() {
    return {
      DATA: data,
      CONDUTOR: condutor,
      CPF: cpf,
      PLACA_CAVALO: placaCavalo,
      VALOR_FRETE: valorFrete,
      AUTORIZACAO_NUM: autorizacaoNum,
    };
  }

  async function executar(nome, tarefa, mensagemSucesso) {
    setStatus("");
    setAcao(nome);
    try {
      await tarefa();
      if (mensagemSucesso) setStatus(mensagemSucesso);
    } catch (err) {
      setStatus(`Erro: ${err.message}`);
    } finally {
      setAcao("");
    }
  }

  function handleEnviar() {
    executar("email", async () => {
      await api.enviarCartaFreteEmail(dados());
      carregarEnviadas();
    }, "E-mail enviado com sucesso.");
  }

  function handleBaixar(formato) {
    executar(formato, () => api.gerarCartaFrete({ ...dados(), formato }));
  }

  function handleAgendar() {
    if (!enviarEm) {
      setStatus("Erro: escolha a data e a hora do envio.");
      return;
    }
    const quando = new Date(enviarEm);
    if (quando <= new Date()) {
      setStatus("Erro: escolha um horário no futuro.");
      return;
    }
    const rotulo = quando.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    executar("agendar", async () => {
      await api.agendarCartaFrete({ ...dados(), enviar_em: quando.toISOString() });
      setEnviarEm("");
      carregarEnviadas();
    }, `Envio agendado para ${rotulo}.`);
  }

  function handleCancelar(carta) {
    if (!window.confirm(`Cancelar o envio agendado da autorização de ${carta.condutor}?`)) return;
    executar("cancelar", async () => {
      await api.cancelarCartaFrete(carta.id);
      carregarEnviadas();
    }, "Envio cancelado.");
  }

  const ocupado = Boolean(acao);

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

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button className="btn-primary" disabled={ocupado} onClick={handleEnviar}>
          {acao === "email" ? "Enviando..." : "Enviar por e-mail"}
        </button>
        <button className="btn-secondary" disabled={ocupado} onClick={() => handleBaixar("pdf")}>
          {acao === "pdf" ? "Gerando..." : "Baixar PDF"}
        </button>
        <button className="btn-secondary" disabled={ocupado} onClick={() => handleBaixar("docx")}>
          {acao === "docx" ? "Gerando..." : "Baixar Word"}
        </button>
        {status && <span style={{ fontSize: 13, color: status.startsWith("Erro") ? "var(--danger)" : "var(--success)" }}>{status}</span>}
      </div>

      <div className="card" style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="field" style={{ minWidth: 230 }}>
          <label>Agendar envio do e-mail para</label>
          <input type="datetime-local" value={enviarEm} min={paraCampoLocal(new Date())} onChange={(e) => setEnviarEm(e.target.value)} />
        </div>
        <button className="btn-secondary" disabled={ocupado} onClick={handleAgendar}>
          {acao === "agendar" ? "Agendando..." : "Agendar envio"}
        </button>
        <span style={{ fontSize: 12, color: "var(--muted)", flex: "1 1 240px" }}>
          O sistema manda sozinho no horário escolhido, com os dados preenchidos acima. Dá para cancelar enquanto não saiu.
        </span>
      </div>

      <div className="card">
        <h2 style={{ margin: "0 0 14px" }}>Autorizações de abastecimento</h2>
        {carregandoLista ? (
          <div className="inline-alert info"><span className="status-dot" />Carregando...</div>
        ) : enviadas.length === 0 ? (
          <div className="inline-alert warning">Nenhuma autorização de abastecimento enviada ou agendada ainda.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Condutor</th>
                  <th>Placa</th>
                  <th>Valor</th>
                  <th>Nº Autorização</th>
                  <th>Envio</th>
                  <th>Situação</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {enviadas.map((c) => {
                  const [rotulo, cor] = SITUACAO[c.status] || [c.status || "Enviada", "var(--muted)"];
                  const programada = c.agendada_para && (c.status === "agendada" || c.status === "cancelada");
                  return (
                    <tr key={c.id}>
                      <td>{c.data}</td>
                      <td>{c.condutor}</td>
                      <td>{c.placa_cavalo}</td>
                      <td>{c.valor_frete}</td>
                      <td>{c.autorizacao_num}</td>
                      <td>{programada ? `para ${formatarEnvio(c.agendada_para)}` : formatarEnvio(c.enviada_em || c.created_at)}</td>
                      <td>
                        <span style={{ color: cor, fontWeight: 600 }} title={c.erro || ""}>{rotulo}</span>
                      </td>
                      <td>
                        {c.status === "agendada" && (
                          <button className="btn-secondary" disabled={ocupado} onClick={() => handleCancelar(c)}>
                            Cancelar
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
