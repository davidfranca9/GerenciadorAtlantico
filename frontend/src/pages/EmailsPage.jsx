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

export default function EmailsPage() {
  const [mensagens, setMensagens] = useState([]);
  const [pagina, setPagina] = useState(1);
  const [total, setTotal] = useState(0);
  const [carregandoLista, setCarregandoLista] = useState(true);
  const [carregandoMais, setCarregandoMais] = useState(false);
  const [erro, setErro] = useState("");
  const [selecionado, setSelecionado] = useState(null);
  const [detalhe, setDetalhe] = useState(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);

  useEffect(() => {
    carregarPagina(1, false);
  }, []);

  async function carregarPagina(numeroPagina, acumular) {
    if (numeroPagina === 1) setCarregandoLista(true);
    else setCarregandoMais(true);
    setErro("");
    try {
      const data = await api.listarEmails(numeroPagina, TAMANHO_PAGINA);
      setMensagens((prev) => (acumular ? [...prev, ...data.mensagens] : data.mensagens));
      setTotal(data.total);
      setPagina(numeroPagina);
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregandoLista(false);
      setCarregandoMais(false);
    }
  }

  async function abrirMensagem(msg) {
    setSelecionado(msg.id);
    setCarregandoDetalhe(true);
    setDetalhe(null);
    setErro("");
    try {
      const data = await api.obterEmail(msg.id);
      setDetalhe(data);
      setMensagens((prev) => prev.map((m) => (m.id === msg.id ? { ...m, lida: true } : m)));
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregandoDetalhe(false);
    }
  }

  const temMais = mensagens.length < total;

  return (
    <div className="ops-page inbox-page">
      {erro && <div className="inline-alert error">{erro}</div>}
      <div className="inbox-layout">
        <section className="card inbox-list">
          <div className="inbox-list-header">
            <strong>Caixa de entrada</strong>
            <span>{total} mensagem{total === 1 ? "" : "s"}</span>
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
          {!selecionado ? (
            <div className="inbox-empty">
              <Icon name="mail" size={32} />
              <p>Selecione uma mensagem para ler.</p>
            </div>
          ) : carregandoDetalhe ? (
            <div className="inline-alert info"><span className="status-dot" />Carregando mensagem...</div>
          ) : detalhe ? (
            <>
              <div className="inbox-detail-header">
                <h2>{detalhe.assunto}</h2>
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
