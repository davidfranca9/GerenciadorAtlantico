import { useEffect, useRef, useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";

function formatarData(iso) {
  if (!iso) return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return data.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const JANELA_24H_MS = 24 * 60 * 60 * 1000;

function formatarRestante(ms) {
  if (ms <= 0) return null;
  const horas = Math.floor(ms / (60 * 60 * 1000));
  const minutos = Math.floor((ms % (60 * 60 * 1000)) / 60000);
  if (horas > 0) return `${horas}h ${minutos}min`;
  return `${minutos}min`;
}

function formatarNumero(numero) {
  // Numeros do WhatsApp vem so com digitos (ex: 557192855288) - formata como +55 71 99999-9999 quando possivel.
  const digitos = String(numero || "").replace(/\D/g, "");
  if (digitos.length < 12) return `+${digitos}`;
  const ddi = digitos.slice(0, 2);
  const ddd = digitos.slice(2, 4);
  const resto = digitos.slice(4);
  const meio = resto.length > 8 ? resto.slice(0, resto.length - 4) : resto.slice(0, 4);
  const fim = resto.slice(meio.length);
  return `+${ddi} ${ddd} ${meio}-${fim}`;
}

export default function WhatsAppPage() {
  const [conversas, setConversas] = useState([]);
  const [carregandoLista, setCarregandoLista] = useState(true);
  const [erro, setErro] = useState("");
  const [selecionado, setSelecionado] = useState(null);
  const [mensagens, setMensagens] = useState([]);
  const [carregandoMensagens, setCarregandoMensagens] = useState(false);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [enviandoArquivo, setEnviandoArquivo] = useState(false);
  const [numeroNovo, setNumeroNovo] = useState("");
  const [editandoNome, setEditandoNome] = useState(false);
  const [nomeEditado, setNomeEditado] = useState("");
  const [salvandoNome, setSalvandoNome] = useState(false);
  const [agora, setAgora] = useState(() => Date.now());
  const [menuAnexoAberto, setMenuAnexoAberto] = useState(false);
  const threadRef = useRef(null);
  const anexoBtnRef = useRef(null);
  const inputDocumentoRef = useRef(null);
  const inputMidiaRef = useRef(null);
  const inputCameraRef = useRef(null);
  const inputAudioRef = useRef(null);

  useEffect(() => {
    const intervalo = setInterval(() => setAgora(Date.now()), 30000);
    return () => clearInterval(intervalo);
  }, []);

  useEffect(() => {
    if (!menuAnexoAberto) return;
    function fechar(e) {
      if (!anexoBtnRef.current?.contains(e.target)) setMenuAnexoAberto(false);
    }
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, [menuAnexoAberto]);

  const ultimaEntrada = [...mensagens].reverse().find((m) => m.direcao === "entrada");
  const prazoRestanteMs = ultimaEntrada ? new Date(ultimaEntrada.created_at).getTime() + JANELA_24H_MS - agora : null;
  const restanteFormatado = prazoRestanteMs != null ? formatarRestante(prazoRestanteMs) : null;

  function nomeDoContato(numero) {
    return conversas.find((c) => c.numero === numero)?.nome || "";
  }

  async function carregarConversas() {
    try {
      const data = await api.listarConversasWhatsapp();
      setConversas(data);
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregandoLista(false);
    }
  }

  useEffect(() => {
    carregarConversas();
    const intervalo = setInterval(carregarConversas, 15000);
    return () => clearInterval(intervalo);
  }, []);

  async function abrirConversa(numero) {
    setSelecionado(numero);
    setEditandoNome(false);
    setCarregandoMensagens(true);
    setErro("");
    try {
      const data = await api.listarMensagensWhatsapp(numero);
      setMensagens(data);
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregandoMensagens(false);
    }
  }

  useEffect(() => {
    if (!selecionado) return;
    const intervalo = setInterval(() => {
      api.listarMensagensWhatsapp(selecionado).then(setMensagens).catch(() => {});
    }, 15000);
    return () => clearInterval(intervalo);
  }, [selecionado]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [mensagens]);

  function abrirEdicaoNome() {
    setNomeEditado(nomeDoContato(selecionado));
    setEditandoNome(true);
  }

  async function handleSalvarNome(e) {
    e.preventDefault();
    setSalvandoNome(true);
    setErro("");
    try {
      await api.salvarContatoWhatsapp(selecionado, nomeEditado.trim());
      setEditandoNome(false);
      carregarConversas();
    } catch (err) {
      setErro(err.message);
    } finally {
      setSalvandoNome(false);
    }
  }

  async function handleAnexar(e) {
    const arquivo = e.target.files?.[0];
    e.target.value = "";
    if (!arquivo) return;
    const numero = (selecionado || numeroNovo.replace(/\D/g, "")).trim();
    if (!numero) { setErro("Informe um número antes de anexar um arquivo."); return; }
    setEnviandoArquivo(true);
    setErro("");
    try {
      await api.enviarArquivoWhatsapp(numero, arquivo, texto.trim());
      setTexto("");
      if (!selecionado) {
        setNumeroNovo("");
        setSelecionado(numero);
      }
      const data = await api.listarMensagensWhatsapp(numero);
      setMensagens(data);
      carregarConversas();
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviandoArquivo(false);
    }
  }

  function acionarInput(ref) {
    setMenuAnexoAberto(false);
    ref.current?.click();
  }

  async function handleEnviar(e) {
    e.preventDefault();
    const numero = (selecionado || numeroNovo.replace(/\D/g, "")).trim();
    if (!numero || !texto.trim()) return;
    setEnviando(true);
    setErro("");
    try {
      await api.enviarMensagemWhatsapp(numero, texto.trim());
      setTexto("");
      if (!selecionado) {
        setNumeroNovo("");
        setSelecionado(numero);
      }
      const data = await api.listarMensagensWhatsapp(numero);
      setMensagens(data);
      carregarConversas();
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="ops-page whatsapp-page">
      {erro && <div className="inline-alert error">{erro}</div>}
      <div className="whatsapp-layout">
        <section className="card whatsapp-list">
          <div className="whatsapp-list-header">
            <strong>Conversas</strong>
            <button className="btn-secondary" onClick={() => { setSelecionado(null); setMensagens([]); }}>
              <Icon name="mail" size={14} />Nova
            </button>
          </div>
          {carregandoLista ? (
            <div className="inline-alert info"><span className="status-dot" />Carregando...</div>
          ) : conversas.length === 0 ? (
            <div className="inline-alert warning">Nenhuma conversa ainda.</div>
          ) : (
            <ul className="whatsapp-conversas">
              {conversas.map((c) => (
                <li key={c.numero}>
                  <button className={`whatsapp-conversa ${selecionado === c.numero ? "active" : ""}`} onClick={() => abrirConversa(c.numero)}>
                    <div className="whatsapp-conversa-top">
                      <strong>{c.nome || formatarNumero(c.numero)}</strong>
                      <span>{formatarData(c.ultima_em)}</span>
                    </div>
                    <div className="whatsapp-conversa-preview">
                      {c.ultima_direcao === "saida" && <Icon name="chevron" size={11} />}
                      {c.ultima_mensagem || "(sem texto)"}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card whatsapp-thread">
          {!selecionado ? (
            <>
              <div className="inline-alert info" style={{ margin: "20px 20px 0" }}>
                Escreva pra um número novo abaixo, ou selecione uma conversa existente ao lado.
              </div>
              <form className="whatsapp-compose-novo" onSubmit={handleEnviar}>
                <div className="field">
                  <label>Número (com DDI e DDD, só números)</label>
                  <input value={numeroNovo} onChange={(e) => setNumeroNovo(e.target.value)} placeholder="5571999999999" />
                </div>
              </form>
            </>
          ) : carregandoMensagens ? (
            <div className="inline-alert info"><span className="status-dot" />Carregando conversa...</div>
          ) : (
            <>
              <div className="whatsapp-thread-header">
                {editandoNome ? (
                  <form className="whatsapp-nome-form" onSubmit={handleSalvarNome}>
                    <input
                      value={nomeEditado}
                      onChange={(e) => setNomeEditado(e.target.value)}
                      placeholder="Nome do contato"
                      autoFocus
                    />
                    <button className="btn-primary" type="submit" disabled={salvandoNome}>{salvandoNome ? "Salvando..." : "Salvar"}</button>
                    <button className="btn-ghost" type="button" onClick={() => setEditandoNome(false)}>Cancelar</button>
                  </form>
                ) : (
                  <>
                    <div>
                      <strong>{nomeDoContato(selecionado) || formatarNumero(selecionado)}</strong>
                      {nomeDoContato(selecionado) && <span className="whatsapp-thread-numero">{formatarNumero(selecionado)}</span>}
                    </div>
                    <button className="btn-secondary" onClick={abrirEdicaoNome}>
                      {nomeDoContato(selecionado) ? "Editar contato" : "Salvar contato"}
                    </button>
                  </>
                )}
              </div>
              <div className="whatsapp-thread-body" ref={threadRef}>
                {mensagens.map((m) => (
                  <div key={m.id} className={`whatsapp-bubble ${m.direcao}`}>
                    {m.tipo !== "texto" && (
                      <div className="whatsapp-bubble-anexo"><Icon name="file" size={13} />{m.nome_arquivo || m.tipo}</div>
                    )}
                    {m.conteudo && <div>{m.conteudo}</div>}
                    <div className="whatsapp-bubble-meta">
                      {formatarData(m.created_at)}
                      {m.status === "erro" && <span className="whatsapp-bubble-erro"> · falhou</span>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {selecionado && ultimaEntrada ? (
            <div className={`inline-alert whatsapp-janela-aviso ${restanteFormatado ? "info" : "error"}`}>
              <Icon name="shield" size={14} />
              {restanteFormatado
                ? <>Janela de resposta livre: <strong>{restanteFormatado}</strong> restantes desde a última mensagem do contato.</>
                : "Janela de 24h expirada — só é possível responder com um modelo de mensagem aprovado pela Meta."}
            </div>
          ) : (
            <div className="inline-alert warning whatsapp-janela-aviso">
              <Icon name="shield" size={14} />
              Só é possível mandar texto livre pra quem escreveu nas últimas 24h. Fora desse prazo, é preciso um modelo de mensagem aprovado pela Meta.
            </div>
          )}

          <form className="whatsapp-compose-bar" onSubmit={handleEnviar}>
            <div className="whatsapp-anexo-wrap" ref={anexoBtnRef}>
              <button
                type="button"
                className="whatsapp-anexo-btn"
                title="Anexar arquivo"
                onClick={() => setMenuAnexoAberto((v) => !v)}
                disabled={enviandoArquivo || enviando || (!selecionado && !numeroNovo.trim())}
              >
                <Icon name="paperclip" size={18} />
              </button>
              {menuAnexoAberto && (
                <div className="whatsapp-anexo-menu">
                  <button type="button" onClick={() => acionarInput(inputDocumentoRef)}>
                    <span className="whatsapp-anexo-icone doc"><Icon name="file" size={16} /></span>Documento
                  </button>
                  <button type="button" onClick={() => acionarInput(inputMidiaRef)}>
                    <span className="whatsapp-anexo-icone midia"><Icon name="upload" size={16} /></span>Fotos e vídeos
                  </button>
                  <button type="button" onClick={() => acionarInput(inputCameraRef)}>
                    <span className="whatsapp-anexo-icone cam"><Icon name="search" size={16} /></span>Câmera
                  </button>
                  <button type="button" onClick={() => acionarInput(inputAudioRef)}>
                    <span className="whatsapp-anexo-icone audio"><Icon name="chat" size={16} /></span>Áudio
                  </button>
                </div>
              )}
              <input ref={inputDocumentoRef} type="file" onChange={handleAnexar} style={{ display: "none" }} />
              <input ref={inputMidiaRef} type="file" accept="image/*,video/*" onChange={handleAnexar} style={{ display: "none" }} />
              <input ref={inputCameraRef} type="file" accept="image/*" capture="environment" onChange={handleAnexar} style={{ display: "none" }} />
              <input ref={inputAudioRef} type="file" accept="audio/*" onChange={handleAnexar} style={{ display: "none" }} />
            </div>
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={enviandoArquivo ? "Enviando arquivo..." : "Escreva uma mensagem..."}
              disabled={enviando || enviandoArquivo || (!selecionado && !numeroNovo.trim())}
            />
            <button className="btn-primary" type="submit" disabled={enviando || enviandoArquivo || !texto.trim() || (!selecionado && !numeroNovo.trim())}>
              <Icon name="mail" size={16} />{enviando ? "Enviando..." : "Enviar"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
