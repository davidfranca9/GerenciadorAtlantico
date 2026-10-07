import { Fragment, useEffect, useState } from "react";
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

// Correcao de valor: o posto ja recebeu a autorizacao, entao a tela mostra o
// que mudou, quando e por que - e o acerto sai na mesma conversa do e-mail.
function FormCorrecao({ carta, ocupado, aoSalvar, aoCancelar }) {
  const [valor, setValor] = useState(carta.valor_frete || "");
  const [motivo, setMotivo] = useState("");
  const [avisar, setAvisar] = useState(true);
  const [erro, setErro] = useState("");

  async function salvar(e) {
    e.preventDefault();
    setErro("");
    try {
      await aoSalvar(valor.trim(), motivo.trim(), avisar);
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="carta-correcao" onSubmit={salvar}>
      <div className="field">
        <label>Novo valor do frete</label>
        <input value={valor} onChange={(e) => setValor(e.target.value)} autoFocus />
      </div>
      <div className="field carta-correcao-motivo">
        <label>Motivo (opcional)</label>
        <input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ex.: valor acertado com o posto" />
      </div>
      <label className="carta-correcao-avisar">
        <input type="checkbox" checked={avisar} onChange={(e) => setAvisar(e.target.checked)} />
        Avisar o posto por e-mail
      </label>
      <div className="carta-correcao-acoes">
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary" disabled={ocupado}>
          {ocupado ? "Salvando..." : avisar ? "Corrigir e reenviar" : "Corrigir só aqui"}
        </button>
      </div>
      <small>
        {avisar
          ? "O acerto vai por e-mail na mesma conversa em que a autorização foi enviada."
          : "Só o nosso registro muda — o posto continua com o valor que recebeu."}
      </small>
      {erro && <div className="inline-alert error">{erro}</div>}
    </form>
  );
}


export default function CartaFretePage() {
  const [data, setData] = useState(hoje());
  const [condutor, setCondutor] = useState("");
  const [cpf, setCpf] = useState("");
  const [placaCavalo, setPlacaCavalo] = useState("");
  const [valorFrete, setValorFrete] = useState("");
  const [autorizacaoNum, setAutorizacaoNum] = useState("");
  const [enviarEm, setEnviarEm] = useState("");
  const [status, setStatus] = useState("");
  const [corrigindo, setCorrigindo] = useState(null);
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

  function handleEnviar(teste = false) {
    executar(teste ? "teste" : "email", async () => {
      await api.enviarCartaFreteEmail({ ...dados(), teste });
      carregarEnviadas();
    }, teste ? "E-mail de teste enviado - foi só pro endereço de teste, o posto não recebeu." : "E-mail enviado com sucesso.");
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

  async function handleCorrigir(carta, valor, motivo, avisar) {
    setStatus("");
    const atualizada = await api.corrigirValorCartaFrete(carta.id, valor, motivo, avisar);
    setCorrigindo(null);
    setStatus(
      avisar
        ? `Correção enviada: o valor de ${carta.condutor} passou para ${atualizada.valor_frete}.`
        : `Valor de ${carta.condutor} corrigido para ${atualizada.valor_frete} (sem aviso ao posto).`
    );
    await carregarEnviadas();
  }

  function handleExcluir(carta) {
    const oque = carta.teste ? "o envio de teste" : `a autorização de ${carta.condutor}`;
    if (!window.confirm(`Apagar ${oque} da lista? O e-mail que já saiu não volta atrás.`)) return;
    executar("excluir", async () => {
      await api.excluirCartaFrete(carta.id);
      carregarEnviadas();
    }, "Registro apagado.");
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
        <button className="btn-secondary" disabled={ocupado} onClick={() => handleEnviar(true)} title="Manda só pro endereço de teste, sem tocar no posto">
          {acao === "teste" ? "Enviando..." : "Enviar teste"}
        </button>
        <button className="btn-primary" disabled={ocupado} onClick={() => handleEnviar(false)}>
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
                  const correcoes = (c.correcoes || []).filter((corr) => !corr.erro);
                  return (
                    <Fragment key={c.id}>
                    <tr>
                      <td>
                        {c.data}
                        {c.teste && <span className="carta-teste" title="Envio de teste: foi só pro endereço de teste e não entra nas faturas">teste</span>}
                      </td>
                      <td>{c.condutor}</td>
                      <td>{c.placa_cavalo}</td>
                      <td>
                        {c.valor_frete}
                        {correcoes.length > 0 && (
                          <span className="carta-corrigida" title={`Valor original: ${correcoes[0].valor_anterior}`}>corrigido</span>
                        )}
                      </td>
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
                        {c.status === "enviada" && (
                          <button className="btn-secondary" disabled={ocupado} onClick={() => setCorrigindo(corrigindo === c.id ? null : c.id)}>
                            {corrigindo === c.id ? "Fechar" : "Corrigir valor"}
                          </button>
                        )}
                        <button className="btn-ghost" disabled={ocupado} title="Apagar este registro da lista" onClick={() => handleExcluir(c)}>
                          Excluir
                        </button>
                      </td>
                    </tr>
                    {(corrigindo === c.id || correcoes.length > 0) && (
                      <tr className="carta-detalhe">
                        <td colSpan={8}>
                          {correcoes.length > 0 && (
                            <ul className="carta-correcoes">
                              {correcoes.map((corr) => (
                                <li key={corr.id}>
                                  <b>{corr.valor_anterior} → {corr.valor_novo}</b>
                                  <span>{formatarEnvio(corr.criado_em)}</span>
                                  {corr.criado_por && <span>por {corr.criado_por}</span>}
                                  {corr.motivo && <em>{corr.motivo}</em>}
                                </li>
                              ))}
                            </ul>
                          )}
                          {corrigindo === c.id && (
                            <FormCorrecao
                              carta={c}
                              ocupado={ocupado}
                              aoCancelar={() => setCorrigindo(null)}
                              aoSalvar={(valor, motivo, avisar) => handleCorrigir(c, valor, motivo, avisar)}
                            />
                          )}
                        </td>
                      </tr>
                    )}
                    </Fragment>
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
