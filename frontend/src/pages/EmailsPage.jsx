import { useEffect, useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";

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

const RASCUNHO_VAZIO = { para: "", assunto: "", corpo: "" };

// Cache em memoria (fora do componente) pra sobreviver a navegacao entre
// paginas do app: sair da tela de E-mails e voltar reaproveita a lista ja
// carregada em vez de buscar tudo de novo. Um refresh de navegador (F5)
// reinicia o modulo JS normalmente, entao esse cache some nesse caso.
const cache = { carregou: false, mensagens: [], pagina: 1, total: 0, selecionado: null, detalhe: null };

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
  const [enviando, setEnviando] = useState(false);
  const [erroEnvio, setErroEnvio] = useState("");

  useEffect(() => {
    if (!cache.carregou) carregarPagina(1, false);
  }, []);

  async function carregarPagina(numeroPagina, acumular) {
    if (numeroPagina === 1) setCarregandoLista(true);
    else setCarregandoMais(true);
    setErro("");
    try {
      const data = await api.listarEmails(numeroPagina, TAMANHO_PAGINA);
      setMensagens((prev) => {
        const novo = acumular ? [...prev, ...data.mensagens] : data.mensagens;
        cache.mensagens = novo;
        return novo;
      });
      setTotal(data.total);
      setPagina(numeroPagina);
      cache.total = data.total;
      cache.pagina = numeroPagina;
      cache.carregou = true;
    } catch (err) {
      setErro(err.message);
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
    setCompor({ ...RASCUNHO_VAZIO, ...rascunho });
  }

  function responder() {
    if (!detalhe) return;
    const original = detalhe.corpo_texto || (detalhe.corpo_html ? detalhe.corpo_html.replace(/<[^>]+>/g, " ") : "");
    abrirComposicao({
      para: detalhe.remetente.email || "",
      assunto: detalhe.assunto?.toLowerCase().startsWith("re:") ? detalhe.assunto : `Re: ${detalhe.assunto || ""}`,
      corpo: `\n\n---\nEm ${formatarData(detalhe.data)}, ${detalhe.remetente.nome || detalhe.remetente.email} escreveu:\n${original.trim()}`,
    });
  }

  async function enviarComposicao() {
    if (!compor) return;
    const destinatarios = compor.para.split(/[,;]/).map((e) => e.trim()).filter(Boolean);
    if (!destinatarios.length) { setErroEnvio("Informe ao menos um destinatário."); return; }
    setEnviando(true);
    setErroEnvio("");
    try {
      await api.enviarEmail({ destinatarios, assunto: compor.assunto, corpo: compor.corpo });
      setCompor(null);
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
                <button className="icon-btn" onClick={() => !enviando && setCompor(null)}><Icon name="close" /></button>
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
                <textarea value={compor.corpo} onChange={(e) => setCompor({ ...compor, corpo: e.target.value })} placeholder="Escreva sua mensagem..." />
              </div>
              <div className="inbox-compose-actions">
                <button className="btn-ghost" disabled={enviando} onClick={() => setCompor(null)}>Cancelar</button>
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
