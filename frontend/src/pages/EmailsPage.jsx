import { useEffect, useRef, useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";

const FORMATOS_TOOLBAR = [
  { comando: "bold", rotulo: "N", titulo: "Negrito", estilo: { fontWeight: 800 } },
  { comando: "italic", rotulo: "I", titulo: "Itálico", estilo: { fontStyle: "italic" } },
  { comando: "underline", rotulo: "S", titulo: "Sublinhado", estilo: { textDecoration: "underline" } },
  { comando: "insertUnorderedList", rotulo: "•", titulo: "Lista" },
];

const TAMANHO_PAGINA = 25;

function formatarData(iso) {
  if (!iso) return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return data.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function escapeHtml(texto) {
  return String(texto).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const RASCUNHO_VAZIO = { para: "", assunto: "", corpoInicial: "" };
const CHAVE_CACHE = "emails_inbox_cache_v1";

function lerCacheSalvo() {
  try {
    const bruto = sessionStorage.getItem(CHAVE_CACHE);
    return bruto ? JSON.parse(bruto) : null;
  } catch {
    return null;
  }
}

function salvarCache(mensagens, pagina, total) {
  try {
    sessionStorage.setItem(CHAVE_CACHE, JSON.stringify({ mensagens, pagina, total }));
  } catch {
    // sessionStorage indisponivel ou cheio: apenas nao persiste, sem quebrar a tela
  }
}

const cacheSalvo = lerCacheSalvo();

// Cache em memoria + sessionStorage pra sobreviver tanto a navegacao entre
// paginas do app (sair de E-mails e voltar) quanto a um F5 de verdade no
// navegador: a lista salva aparece instantaneamente, e uma busca silenciosa
// em segundo plano atualiza os dados sem mostrar tela de carregamento.
const cache = {
  carregou: Boolean(cacheSalvo),
  mensagens: cacheSalvo?.mensagens || [],
  pagina: cacheSalvo?.pagina || 1,
  total: cacheSalvo?.total || 0,
  selecionado: null,
  detalhe: null,
};

export default function EmailsPage() {
  const [mensagens, setMensagens] = useState(cache.mensagens);
  const [pagina, setPagina] = useState(cache.pagina);
  const [total, setTotal] = useState(cache.total);
  const [carregandoLista, setCarregandoLista] = useState(!cache.carregou);
  const [carregandoMais, setCarregandoMais] = useState(false);
  const [erro, setErro] = useState("");
  const [selecionado, setSelecionado] = useState(cache.selecionado);
  const [detalhe, setDetalhe] = useState(cache.detalhe);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const [compor, setCompor] = useState(null);
  const [composeKey, setComposeKey] = useState(0);
  const [anexos, setAnexos] = useState([]);
  const [enviando, setEnviando] = useState(false);
  const [erroEnvio, setErroEnvio] = useState("");
  const corpoRef = useRef(null);

  useEffect(() => {
    // Se ja tem algo em cache, mostra na hora e so atualiza por baixo dos
    // panos (sem spinner); senao, e a primeira vez e mostra o carregamento.
    carregarPagina(1, false, !cache.carregou);
  }, []);

  async function carregarPagina(numeroPagina, acumular, mostrarCarregando = true) {
    if (mostrarCarregando) {
      if (numeroPagina === 1) setCarregandoLista(true);
      else setCarregandoMais(true);
    }
    setErro("");
    try {
      const data = await api.listarEmails(numeroPagina, TAMANHO_PAGINA);
      setMensagens((prev) => {
        const novo = acumular ? [...prev, ...data.mensagens] : data.mensagens;
        cache.mensagens = novo;
        salvarCache(novo, numeroPagina, data.total);
        return novo;
      });
      setTotal(data.total);
      setPagina(numeroPagina);
      cache.total = data.total;
      cache.pagina = numeroPagina;
      cache.carregou = true;
    } catch (err) {
      if (mostrarCarregando) setErro(err.message);
    } finally {
      setCarregandoLista(false);
      setCarregandoMais(false);
    }
  }

  async function abrirMensagem(msg) {
    setCompor(null);
    setSelecionado(msg.id);
    cache.selecionado = msg.id;
    setCarregandoDetalhe(true);
    setDetalhe(null);
    setErro("");
    try {
      const data = await api.obterEmail(msg.id);
      setDetalhe(data);
      cache.detalhe = data;
      setMensagens((prev) => {
        const novo = prev.map((m) => (m.id === msg.id ? { ...m, lida: true } : m));
        cache.mensagens = novo;
        salvarCache(novo, cache.pagina, cache.total);
        return novo;
      });
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregandoDetalhe(false);
    }
  }

  function abrirComposicao(rascunho) {
    setErroEnvio("");
    setAnexos([]);
    setComposeKey((k) => k + 1);
    setCompor({ ...RASCUNHO_VAZIO, ...rascunho });
  }

  function fecharComposicao() {
    if (enviando) return;
    setCompor(null);
    setAnexos([]);
  }

  function aplicarFormatacao(comando) {
    document.execCommand(comando, false, null);
  }

  function adicionarAnexos(e) {
    const novos = Array.from(e.target.files || []);
    e.target.value = "";
    setAnexos((prev) => [...prev, ...novos]);
  }

  function removerAnexo(indice) {
    setAnexos((prev) => prev.filter((_, i) => i !== indice));
  }

  function responder() {
    if (!detalhe) return;
    const original = detalhe.corpo_html || `<pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(detalhe.corpo_texto || "")}</pre>`;
    const citacao = `<br><br><div style="border-left:2px solid #ccc;margin-left:4px;padding-left:10px;color:#666">Em ${formatarData(detalhe.data)}, ${escapeHtml(detalhe.remetente.nome || detalhe.remetente.email)} escreveu:<br>${original}</div>`;
    abrirComposicao({
      para: detalhe.remetente.email || "",
      assunto: detalhe.assunto?.toLowerCase().startsWith("re:") ? detalhe.assunto : `Re: ${detalhe.assunto || ""}`,
      corpoInicial: citacao,
    });
  }

  async function enviarComposicao() {
    if (!compor) return;
    const destinatarios = compor.para.split(/[,;]/).map((e) => e.trim()).filter(Boolean);
    if (!destinatarios.length) { setErroEnvio("Informe ao menos um destinatário."); return; }
    setEnviando(true);
    setErroEnvio("");
    try {
      const corpoHtml = corpoRef.current?.innerHTML || "";
      await api.enviarEmail({ destinatarios, assunto: compor.assunto, corpo: corpoHtml, anexos });
      setCompor(null);
      setAnexos([]);
    } catch (err) {
      setErroEnvio(err.message);
    } finally {
      setEnviando(false);
    }
  }

  const temMais = mensagens.length < total;

  return (
    <div className="ops-page inbox-page">
      {erro && <div className="inline-alert error">{erro}</div>}
      <div className="inbox-layout">
        <section className="card inbox-list">
          <div className="inbox-list-header">
            <div><strong>Caixa de entrada</strong><span>{total} mensagem{total === 1 ? "" : "s"}</span></div>
            <button className="btn-primary inbox-compose-btn" onClick={() => abrirComposicao({})}>
              <Icon name="mail" size={16} />Escrever
            </button>
          </div>
          {carregandoLista ? (
            <div className="inline-alert info"><span className="status-dot" />Carregando mensagens...</div>
          ) : mensagens.length === 0 ? (
            <div className="inline-alert warning">Nenhuma mensagem encontrada.</div>
          ) : (
            <ul className="inbox-messages">
              {mensagens.map((msg) => (
                <li key={msg.id}>
                  <button
                    className={`inbox-message ${msg.lida ? "" : "unread"} ${selecionado === msg.id ? "active" : ""}`}
                    onClick={() => abrirMensagem(msg)}
                  >
                    <div className="inbox-message-top">
                      <strong>{msg.remetente.nome || msg.remetente.email || "Desconhecido"}</strong>
                      <span>{formatarData(msg.data)}</span>
                    </div>
                    <div className="inbox-message-subject">{msg.assunto}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {temMais && (
            <button className="btn-ghost inbox-load-more" disabled={carregandoMais} onClick={() => carregarPagina(pagina + 1, true)}>
              {carregandoMais ? "Carregando..." : "Carregar mais"}
            </button>
          )}
        </section>
        <section className="card inbox-detail">
          {compor ? (
            <div className="inbox-compose-inline">
              <div className="inbox-compose-header">
                <strong>Novo e-mail</strong>
                <button className="icon-btn" onClick={fecharComposicao}><Icon name="close" /></button>
              </div>
              {erroEnvio && <div className="inline-alert error">{erroEnvio}</div>}
              <div className="field">
                <label>Para</label>
                <input value={compor.para} onChange={(e) => setCompor({ ...compor, para: e.target.value })} placeholder="destinatario@exemplo.com, outro@exemplo.com" />
              </div>
              <div className="field">
                <label>Assunto</label>
                <input value={compor.assunto} onChange={(e) => setCompor({ ...compor, assunto: e.target.value })} placeholder="Assunto do e-mail" />
              </div>
              <div className="field inbox-compose-body-field">
                <label>Mensagem</label>
                <div className="inbox-compose-toolbar">
                  {FORMATOS_TOOLBAR.map((f) => (
                    <button key={f.comando} type="button" title={f.titulo} style={f.estilo} onMouseDown={(e) => e.preventDefault()} onClick={() => aplicarFormatacao(f.comando)}>
                      {f.rotulo}
                    </button>
                  ))}
                </div>
                <div
                  key={composeKey}
                  ref={corpoRef}
                  className="inbox-compose-editor"
                  contentEditable
                  suppressContentEditableWarning
                  data-placeholder="Escreva sua mensagem..."
                  dangerouslySetInnerHTML={{ __html: compor.corpoInicial || "" }}
                />
              </div>
              <div className="field">
                <label>Anexos</label>
                <label className="inbox-attach-btn">
                  <Icon name="upload" size={14} />Anexar arquivo
                  <input type="file" multiple onChange={adicionarAnexos} style={{ display: "none" }} />
                </label>
                {anexos.length > 0 && (
                  <ul className="inbox-attach-list">
                    {anexos.map((arquivo, indice) => (
                      <li key={`${arquivo.name}-${indice}`}>
                        <Icon name="file" size={13} /><span>{arquivo.name}</span>
                        <button type="button" onClick={() => removerAnexo(indice)}><Icon name="close" size={12} /></button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="inbox-compose-actions">
                <button className="btn-ghost" disabled={enviando} onClick={fecharComposicao}>Cancelar</button>
                <button className="btn-primary" disabled={enviando} onClick={enviarComposicao}>
                  <Icon name="mail" size={16} />{enviando ? "Enviando..." : "Enviar"}
                </button>
              </div>
            </div>
          ) : !selecionado ? (
            <div className="inbox-empty">
              <Icon name="mail" size={32} />
              <p>Selecione uma mensagem para ler.</p>
            </div>
          ) : carregandoDetalhe ? (
            <div className="inline-alert info"><span className="status-dot" />Carregando mensagem...</div>
          ) : detalhe ? (
            <>
              <div className="inbox-detail-header">
                <div className="inbox-detail-header-top">
                  <h2>{detalhe.assunto}</h2>
                  <button className="btn-ghost" onClick={responder}><Icon name="mail" size={14} />Responder</button>
                </div>
                <div>
                  <strong>{detalhe.remetente.nome || detalhe.remetente.email}</strong>{" "}
                  <span>&lt;{detalhe.remetente.email}&gt;</span>
                </div>
                <small>{formatarData(detalhe.data)}</small>
              </div>
              {detalhe.anexos?.length > 0 && (
                <div className="inbox-detail-attachments">
                  <Icon name="file" size={14} /> {detalhe.anexos.join(", ")}
                </div>
              )}
              <iframe
                title="Corpo do e-mail"
                className="inbox-detail-body"
                sandbox=""
                srcDoc={
                  detalhe.corpo_html ||
                  `<pre style="white-space:pre-wrap;font-family:inherit;margin:0">${escapeHtml(detalhe.corpo_texto || "(mensagem vazia)")}</pre>`
                }
              />
            </>
          ) : null}
        </section>
      </div>
    </div>
  );
}
