import { useEffect, useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";

const EMAIL_VALIDO = /^[^@\s,;<>]+@[^@\s,;<>]+\.[a-z]{2,}$/i;

function formatarQuando(iso) {
  if (!iso) return "";
  const data = new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(data.getTime())
    ? ""
    : data.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function mesmaLista(a, b) {
  return a.length === b.length && a.every((email, i) => email === b[i]);
}

function ListaEmailCard({ lista, aoSalvar }) {
  const [rascunho, setRascunho] = useState(lista.emails);
  const [novo, setNovo] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => setRascunho(lista.emails), [lista]);

  const mudou = !mesmaLista(rascunho, lista.emails);

  function incluir(e) {
    e.preventDefault();
    const email = novo.trim().toLowerCase();
    if (!email) return;
    if (!EMAIL_VALIDO.test(email)) {
      setErro(`"${novo.trim()}" não é um e-mail válido.`);
      return;
    }
    if (rascunho.includes(email)) {
      setErro(`${email} já está na lista.`);
      return;
    }
    setRascunho([...rascunho, email]);
    setNovo("");
    setErro("");
    setSalvo(false);
  }

  function remover(email) {
    setRascunho(rascunho.filter((e) => e !== email));
    setErro("");
    setSalvo(false);
  }

  async function executar(acao) {
    setSalvando(true);
    setErro("");
    try {
      aoSalvar(await acao());
      setSalvo(true);
    } catch (err) {
      setErro(err.message);
    } finally {
      setSalvando(false);
    }
  }

  function salvar() {
    if (rascunho.length === 0) {
      setErro("A lista precisa de pelo menos um e-mail.");
      return;
    }
    executar(() => api.salvarListaEmail(lista.chave, rascunho));
  }

  function voltarAoPadrao() {
    if (!window.confirm(`Voltar a lista "${lista.nome}" para os e-mails padrão do sistema?`)) return;
    executar(() => api.restaurarListaEmail(lista.chave));
  }

  return (
    <section className="card lista-email">
      <div className="lista-email-topo">
        <strong>{lista.nome}</strong>
        <span className={`lista-email-selo ${lista.personalizada ? "alterada" : ""}`}>
          {lista.personalizada ? "Alterada" : "Padrão"}
        </span>
      </div>
      <p className="lista-email-uso">{lista.uso}</p>

      <ul className="lista-email-chips">
        {rascunho.map((email) => (
          <li key={email}>
            <span title={email}>{email}</span>
            <button type="button" onClick={() => remover(email)} aria-label={`Remover ${email}`} title="Remover">
              <Icon name="close" size={12} />
            </button>
          </li>
        ))}
        {rascunho.length === 0 && <li className="vazia">Nenhum e-mail: inclua pelo menos um.</li>}
      </ul>

      <form className="lista-email-incluir" onSubmit={incluir}>
        <input
          type="text"
          inputMode="email"
          value={novo}
          onChange={(e) => { setNovo(e.target.value); setErro(""); }}
          placeholder="novo@email.com"
          aria-label={`Incluir e-mail em ${lista.nome}`}
        />
        <button type="submit" className="btn-secondary"><Icon name="plus" size={14} />Incluir</button>
      </form>

      {erro && <div className="lista-email-erro">{erro}</div>}

      <div className="lista-email-rodape">
        <span>
          {salvo && !mudou ? (
            <span className="lista-email-ok">Salvo. Vale a partir do próximo envio.</span>
          ) : lista.personalizada ? (
            `Alterada${lista.atualizado_por ? ` por ${lista.atualizado_por}` : ""}${lista.atualizado_em ? ` em ${formatarQuando(lista.atualizado_em)}` : ""}`
          ) : (
            "Lista padrão do sistema"
          )}
        </span>
        <div className="lista-email-acoes">
          {mudou ? (
            <>
              <button type="button" className="btn-ghost" disabled={salvando} onClick={() => { setRascunho(lista.emails); setErro(""); }}>
                Descartar
              </button>
              <button type="button" className="btn-primary" disabled={salvando} onClick={salvar}>
                {salvando ? "Salvando..." : "Salvar"}
              </button>
            </>
          ) : (
            lista.personalizada && (
              <button type="button" className="btn-ghost" disabled={salvando} onClick={voltarAoPadrao}>
                Voltar ao padrão
              </button>
            )
          )}
        </div>
      </div>
    </section>
  );
}

export default function ConfiguracoesPage() {
  const [listas, setListas] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api.listarListasEmail().then(setListas).catch((err) => setErro(err.message));
  }, []);

  function atualizar(lista) {
    setListas((atuais) => atuais.map((l) => (l.chave === lista.chave ? lista : l)));
  }

  return (
    <div className="ops-page config-page">
      <div className="config-intro">
        <h2>Listas de e-mail</h2>
        <p>Pra quem cada e-mail do sistema vai. A mudança vale a partir do próximo envio.</p>
      </div>
      {erro && <div className="inline-alert error">{erro}</div>}
      {!listas && !erro && <div className="inline-alert info"><span className="status-dot" />Carregando listas...</div>}
      {listas && (
        <div className="listas-email-grid">
          {listas.map((lista) => (
            <ListaEmailCard key={lista.chave} lista={lista} aoSalvar={atualizar} />
          ))}
        </div>
      )}
    </div>
  );
}
