import { useCallback, useEffect, useMemo, useState } from "react";
import { financeiro as api } from "../../api/client";
import Icon from "../../components/Icon";
import { Aviso, CampoValor, Dinheiro, ImportarPlanilha, Modal } from "./comum";
import {
  FORMAS, brl, dataDe, diaBr, diaCurto, diaPorExtenso, formaInfo, hojeIso, isoDe, numeroBr, periodoDe, rotuloPeriodo, somarDias, valorParaCampo,
} from "./formato";
import "./financeiro.css";

const PERIODOS = [
  { valor: "dia", rotulo: "Dia" },
  { valor: "semana", rotulo: "Semana" },
  { valor: "mes", rotulo: "Mês" },
];

function GraficoSaldo({ serie }) {
  const [foco, setFoco] = useState(null);
  if (!serie?.length) return null;
  const largura = 360;
  const altura = 110;
  const margem = { topo: 12, base: 20, lado: 4 };
  const valores = serie.map((p) => p.saldo);
  let minimo = Math.min(...valores);
  let maximo = Math.max(...valores);
  if (maximo - minimo < 1) {
    minimo -= 1;
    maximo += 1;
  }
  const folga = (maximo - minimo) * 0.12;
  const x = (i) => margem.lado + (i / Math.max(1, serie.length - 1)) * (largura - margem.lado * 2);
  const y = (v) => margem.topo + (1 - (v - (minimo - folga)) / (maximo + folga - (minimo - folga))) * (altura - margem.topo - margem.base);
  const linha = serie.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.saldo).toFixed(1)}`).join(" ");
  const area = `${linha} L${x(serie.length - 1).toFixed(1)},${altura - margem.base} L${x(0).toFixed(1)},${altura - margem.base} Z`;
  const ponto = foco ?? serie.length - 1;

  function mover(e) {
    const caixa = e.currentTarget.getBoundingClientRect();
    const proporcao = (e.clientX - caixa.left) / caixa.width;
    setFoco(Math.max(0, Math.min(serie.length - 1, Math.round(proporcao * (serie.length - 1)))));
  }

  return (
    <figure className="fin-grafico-saldo">
      <figcaption>
        <span>{foco === null ? "Saldo nos últimos 30 dias" : diaPorExtenso(serie[ponto].data)}</span>
        <strong>{brl(serie[ponto].saldo)}</strong>
      </figcaption>
      <svg viewBox={`0 0 ${largura} ${altura}`} role="img" aria-label="Evolução do saldo total" onMouseMove={mover} onMouseLeave={() => setFoco(null)}>
        <defs>
          <linearGradient id="fin-saldo-gradiente" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" style={{ stopColor: "var(--accent)", stopOpacity: 0.28 }} />
            <stop offset="100%" style={{ stopColor: "var(--accent)", stopOpacity: 0 }} />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} className="fin-grade" x1="0" x2={largura} y1={margem.topo + f * (altura - margem.topo - margem.base)} y2={margem.topo + f * (altura - margem.topo - margem.base)} />
        ))}
        <path d={area} fill="url(#fin-saldo-gradiente)" />
        <path d={linha} className="fin-linha-saldo" />
        <line className="fin-guia" x1={x(ponto)} x2={x(ponto)} y1={margem.topo - 4} y2={altura - margem.base} />
        <circle className="fin-ponto-saldo" cx={x(ponto)} cy={y(serie[ponto].saldo)} r="4.5" />
        <text className="fin-eixo" x="2" y={altura - 5}>{diaCurto(serie[0].data)}</text>
        <text className="fin-eixo" x={largura - 2} y={altura - 5} textAnchor="end">{diaCurto(serie[serie.length - 1].data)}</text>
      </svg>
    </figure>
  );
}

function Distribuicao({ contas }) {
  const positivas = contas.filter((c) => c.fechamento > 0);
  const total = positivas.reduce((soma, c) => soma + c.fechamento, 0);
  if (!total) return null;
  return (
    <div className="fin-distribuicao">
      <div className="fin-distribuicao-barra" role="img" aria-label="Divisão do saldo entre os bancos">
        {positivas.map((c) => (
          <span key={c.id} style={{ width: `${(c.fechamento / total) * 100}%`, background: c.cor || "var(--muted)" }} title={`${c.nome}: ${brl(c.fechamento)}`} />
        ))}
      </div>
      <ul>
        {positivas.map((c) => (
          <li key={c.id}>
            <i style={{ background: c.cor || "var(--muted)" }} />
            {c.nome} <b>{Math.round((c.fechamento / total) * 100)}%</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CartaoBanco({ conta, ativo, aoClicar }) {
  const variacao = conta.fechamento - conta.abertura;
  return (
    <button type="button" className={`fin-banco ${ativo ? "ativo" : ""}`} style={{ "--cor-banco": conta.cor || "var(--muted)" }} onClick={aoClicar} aria-pressed={ativo}>
      <span className="fin-banco-nome"><i />{conta.nome}</span>
      <Dinheiro valor={conta.fechamento} tamanho="m" />
      <span className="fin-banco-abriu">abriu com {brl(conta.abertura)}</span>
      <span className="fin-banco-movimento">
        <span className="entrada">{brl(conta.entradas, { sinal: true })}</span>
        <span className="saida">{brl(-conta.saidas)}</span>
      </span>
      {Math.abs(variacao) >= 0.01 && <span className={`fin-banco-variacao ${variacao > 0 ? "sobe" : "desce"}`}>{variacao > 0 ? "▲" : "▼"}</span>}
    </button>
  );
}

function EditorLancamento({ lancamento, contas, aoSalvar, aoExcluir, aoCancelar }) {
  const [valor, setValor] = useState(valorParaCampo(lancamento.valor));
  const [descricao, setDescricao] = useState(lancamento.descricao);
  const [data, setData] = useState(lancamento.data);
  const [forma, setForma] = useState(lancamento.forma);
  const [contaId, setContaId] = useState(lancamento.conta_id);
  const [erro, setErro] = useState("");
  const [confirmarExclusao, setConfirmarExclusao] = useState(false);

  async function salvar(e) {
    e.preventDefault();
    const numero = numeroBr(valor);
    if (!numero || numero <= 0) return setErro("Informe um valor maior que zero");
    try {
      await aoSalvar({ valor: numero, descricao, data, forma, conta_id: lancamento.transferencia ? undefined : Number(contaId) });
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="fin-editor-lancamento" onSubmit={salvar}>
      <div className="fin-editor-grade">
        <label className="field"><span>Valor</span><CampoValor valor={valor} aoMudar={setValor} autoFocus /></label>
        <label className="field"><span>Data</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></label>
        <label className="field fin-editor-largo"><span>Descrição</span><input value={descricao} onChange={(e) => setDescricao(e.target.value)} /></label>
        {!lancamento.transferencia && (
          <>
            <label className="field"><span>Forma</span>
              <select value={forma} onChange={(e) => setForma(e.target.value)}>
                {FORMAS.map((f) => <option key={f.valor} value={f.valor}>{f.rotulo}</option>)}
              </select>
            </label>
            <label className="field"><span>Conta</span>
              <select value={contaId} onChange={(e) => setContaId(e.target.value)}>
                {contas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
              </select>
            </label>
          </>
        )}
      </div>
      {lancamento.transferencia && <small className="fin-dica">Numa transferência, data e valor mudam nas duas contas.</small>}
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-editor-acoes">
        {confirmarExclusao ? (
          <span className="fin-confirmar">
            {lancamento.transferencia ? "Apagar a transferência nas duas contas?" : "Apagar este lançamento?"}
            <button type="button" className="btn-ghost perigo" onClick={aoExcluir}>Apagar</button>
            <button type="button" className="btn-ghost" onClick={() => setConfirmarExclusao(false)}>Não</button>
          </span>
        ) : (
          <button type="button" className="btn-ghost perigo" onClick={() => setConfirmarExclusao(true)}><Icon name="trash" size={14} /> Excluir</button>
        )}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary">Salvar</button>
      </div>
    </form>
  );
}

function LinhaLancamento({ item, aberto, aoAbrir, children }) {
  const transferencia = Boolean(item.transferencia);
  const forma = formaInfo(item.forma);
  const tipo = transferencia ? "transferencia" : item.tipo;
  const subtitulo = transferencia
    ? `${item.tipo === "saida" ? item.conta : item.contraparte || "?"} → ${item.tipo === "saida" ? item.contraparte || "?" : item.conta}`
    : `${forma.rotulo} · ${item.conta}`;
  return (
    <li className={`fin-lancamento ${tipo} ${aberto ? "aberto" : ""}`}>
      <button type="button" className="fin-lancamento-linha" onClick={aoAbrir} aria-expanded={aberto}>
        <span className="fin-lancamento-icone"><Icon name={transferencia ? "transfer" : forma.icone} size={16} /></span>
        <span className="fin-lancamento-texto">
          <strong>{transferencia ? "Transferência entre contas" : item.descricao || forma.rotulo}</strong>
          <small>
            {!transferencia && <i style={{ background: item.cor || "var(--muted)" }} />}
            {subtitulo}
            {item.origem === "extrato" && <em>extrato</em>}
            {item.origem === "agenda" && <em>conta paga</em>}
          </small>
        </span>
        <Dinheiro
          valor={transferencia ? item.valor : item.tipo === "entrada" ? item.valor : -item.valor}
          sinal={!transferencia}
          tamanho="s"
          className="fin-lancamento-valor"
        />
      </button>
      {aberto && children}
    </li>
  );
}

function NovoLancamento({ contas, diaPadrao, aoLancar }) {
  const [tipo, setTipo] = useState("saida");
  const [valor, setValor] = useState("");
  const [forma, setForma] = useState("PIX");
  const [contaId, setContaId] = useState(contas[0]?.id || "");
  const [destinoId, setDestinoId] = useState(contas[1]?.id || "");
  const [descricao, setDescricao] = useState("");
  const [data, setData] = useState(diaPadrao);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [ultimo, setUltimo] = useState("");

  useEffect(() => setData(diaPadrao), [diaPadrao]);
  useEffect(() => {
    if (!contas.some((c) => String(c.id) === String(contaId))) setContaId(contas[0]?.id || "");
  }, [contas, contaId]);

  async function lancar(e) {
    e.preventDefault();
    setErro("");
    const numero = numeroBr(valor);
    if (!numero || numero <= 0) return setErro("Informe o valor");
    if (tipo === "transferencia" && String(contaId) === String(destinoId)) return setErro("Escolha contas diferentes");
    setEnviando(true);
    try {
      await aoLancar({
        tipo, valor: numero, data, descricao: descricao.trim(), forma: tipo === "transferencia" ? "TRANSFERENCIA" : forma,
        conta_id: Number(contaId), conta_destino_id: tipo === "transferencia" ? Number(destinoId) : undefined,
      });
      setUltimo(`${tipo === "entrada" ? "Entrada" : tipo === "saida" ? "Saída" : "Transferência"} de ${brl(numero)} lançada.`);
      setValor("");
      setDescricao("");
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  }

  const escolherConta = (atual, aoEscolher, rotulo) => (
    <fieldset className="fin-escolha-conta">
      <legend>{rotulo}</legend>
      {contas.map((c) => (
        <label key={c.id} className={String(atual) === String(c.id) ? "marcado" : ""} style={{ "--cor-banco": c.cor || "var(--muted)" }}>
          <input type="radio" name={rotulo} checked={String(atual) === String(c.id)} onChange={() => aoEscolher(c.id)} />
          <i />{c.nome}
        </label>
      ))}
    </fieldset>
  );

  return (
    <form className={`card fin-composer ${tipo}`} onSubmit={lancar}>
      <h3>Novo lançamento</h3>
      <div className="fin-tipo" role="tablist">
        {[["entrada", "Entrada"], ["saida", "Saída"], ["transferencia", "Entre contas"]].map(([v, r]) => (
          <button key={v} type="button" role="tab" aria-selected={tipo === v} className={tipo === v ? "ativo" : ""} onClick={() => setTipo(v)}>{r}</button>
        ))}
      </div>
      <CampoValor valor={valor} aoMudar={setValor} grande id="fin-novo-valor" />
      {tipo !== "transferencia" && (
        <div className="fin-formas">
          {FORMAS.map((f) => (
            <button key={f.valor} type="button" className={forma === f.valor ? "ativo" : ""} onClick={() => setForma(f.valor)}>
              <Icon name={f.icone} size={13} />{f.rotulo}
            </button>
          ))}
        </div>
      )}
      {tipo === "transferencia" ? (
        <>
          {escolherConta(contaId, setContaId, "Sai de")}
          {escolherConta(destinoId, setDestinoId, "Entra em")}
        </>
      ) : escolherConta(contaId, setContaId, tipo === "entrada" ? "Entrou em" : "Saiu de")}
      <label className="field"><span>Descrição</span>
        <input value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder={tipo === "entrada" ? "Ex.: Fertimaxi, frete 5003" : "Ex.: Posto Mar Vida"} />
      </label>
      <label className="field"><span>Data</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></label>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      {ultimo && !erro && <Aviso>{ultimo}</Aviso>}
      <button type="submit" className="btn-primary fin-lancar" disabled={enviando || !contas.length}>
        {enviando ? "Lançando..." : tipo === "entrada" ? "Lançar entrada" : tipo === "saida" ? "Lançar saída" : "Transferir"}
      </button>
    </form>
  );
}

function ImportarExtrato({ contas, aoFechar, aoImportar }) {
  const [contaId, setContaId] = useState(contas[0]?.id || "");
  const [arquivo, setArquivo] = useState(null);
  const [previa, setPrevia] = useState(null);
  const [feito, setFeito] = useState(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function ler(novoArquivo = arquivo, novaConta = contaId) {
    if (!novoArquivo || !novaConta) return;
    setErro("");
    setPrevia(null);
    setFeito(null);
    setCarregando(true);
    try {
      setPrevia(await api.importarExtrato(novaConta, novoArquivo, false));
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  }

  async function aplicar() {
    setCarregando(true);
    try {
      const resultado = await api.importarExtrato(contaId, arquivo, true);
      setFeito(resultado);
      aoImportar();
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  }

  const resumo = feito || previa;
  return (
    <Modal titulo="Importar extrato do banco" subtitulo="Arquivo OFX baixado no internet banking" aoFechar={aoFechar}>
      <label className="field"><span>Conta</span>
        <select value={contaId} onChange={(e) => { setContaId(e.target.value); ler(arquivo, e.target.value); }}>
          {contas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
        </select>
      </label>
      <label className={`fin-soltar ${arquivo ? "com-arquivo" : ""}`}>
        <input type="file" accept=".ofx,.OFX" onChange={(e) => { const f = e.target.files?.[0]; setArquivo(f); ler(f); }} />
        <Icon name="upload" size={20} />
        <span><strong>{arquivo ? arquivo.name : "Escolher arquivo OFX"}</strong><small>Nubank, Banco do Brasil, Itaú e Sicredi exportam OFX</small></span>
      </label>
      {carregando && <Aviso>Lendo o extrato...</Aviso>}
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      {resumo && (
        <div className="fin-previa">
          <p className="fin-previa-titulo">
            {feito ? "Importado:" : "Vão entrar"} <strong>{resumo.lancamentos.novos} lançamentos</strong>
            {resumo.periodo && ` de ${diaBr(resumo.periodo.inicio)} a ${diaBr(resumo.periodo.fim)}`}
            {resumo.lancamentos.ja_existiam > 0 && ` · ${resumo.lancamentos.ja_existiam} já importados antes`}
            {resumo.lancamentos.parecidos_ignorados > 0 && ` · ${resumo.lancamentos.parecidos_ignorados} já lançados à mão (mesmo dia e valor) ficaram de fora`}
          </p>
          {resumo.conferencia && (
            <ul className="fin-conferido">
              <li className={Math.abs(resumo.conferencia.diferenca) < 0.01 ? "bate" : "diverge"}>
                <span>Saldo em {diaBr(resumo.conferencia.data)}</span>
                <span className="fin-conferido-valores"><small>banco {brl(resumo.conferencia.banco)}</small><strong>sistema {brl(resumo.conferencia.sistema)}</strong></span>
                <Icon name={Math.abs(resumo.conferencia.diferenca) < 0.01 ? "check" : "alert"} size={15} />
              </li>
            </ul>
          )}
          {!feito && resumo.previa?.length > 0 && (
            <ul className="fin-previa-lista">
              {resumo.previa.map((l, i) => (
                <li key={i}>
                  <span>{diaCurto(l.data)}</span>
                  <span>{l.descricao}</span>
                  <b className={l.tipo}>{brl(l.tipo === "entrada" ? l.valor : -l.valor, { sinal: true })}</b>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <footer className="fin-modal-rodape">
        <button type="button" className="btn-secondary" onClick={aoFechar}>{feito ? "Fechar" : "Cancelar"}</button>
        {!feito && <button type="button" className="btn-primary" disabled={!previa || !previa.lancamentos.novos || carregando} onClick={aplicar}>Importar lançamentos</button>}
      </footer>
    </Modal>
  );
}

function PrimeiraConta({ aoCriar, aoImportar }) {
  const [nome, setNome] = useState("");
  const [saldo, setSaldo] = useState("");
  const [data, setData] = useState(hojeIso());
  const [erro, setErro] = useState("");

  async function criar(e) {
    e.preventDefault();
    try {
      await aoCriar({ nome: nome.trim(), saldo_inicial: numeroBr(saldo) || 0, saldo_inicial_em: data });
      setNome("");
      setSaldo("");
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <section className="card fin-vazio">
      <div>
        <span className="eyebrow">COMEÇAR</span>
        <h2>Traga o caixa da planilha</h2>
        <p>A importação cria os bancos com o saldo do dia e todos os lançamentos. Os totais são conferidos com os da planilha antes de gravar.</p>
        <button type="button" className="btn-primary" onClick={aoImportar}><Icon name="upload" size={15} /> Importar Fluxo de Caixa</button>
      </div>
      <form onSubmit={criar}>
        <strong>Ou cadastre um banco</strong>
        <label className="field"><span>Nome</span><input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Nubank" required /></label>
        <label className="field"><span>Saldo no começo do dia</span><CampoValor valor={saldo} aoMudar={setSaldo} /></label>
        <label className="field"><span>Dia</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></label>
        {erro && <Aviso tipo="error">{erro}</Aviso>}
        <button type="submit" className="btn-secondary">Cadastrar banco</button>
      </form>
    </section>
  );
}

export default function CaixaPage() {
  const [periodo, setPeriodo] = useState("dia");
  const [dia, setDia] = useState(hojeIso());
  const [contaFiltro, setContaFiltro] = useState(null);
  const [filtroTipo, setFiltroTipo] = useState("todos");
  const [busca, setBusca] = useState("");
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [abertoId, setAbertoId] = useState(null);
  const [modal, setModal] = useState(null);
  const [primeiraCarga, setPrimeiraCarga] = useState(true);

  const { inicio, fim } = periodoDe(periodo, dia);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      setDados(await api.caixa(inicio, fim));
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  }, [inicio, fim]);

  useEffect(() => { carregar(); }, [carregar]);

  // Sem nada no dia de hoje, abre no ultimo dia com movimento (ex.: a
  // planilha importada de ontem).
  useEffect(() => {
    if (!primeiraCarga || !dados) return;
    setPrimeiraCarga(false);
    if (dados.lancamentos.length === 0 && dados.ultimo_movimento && dados.ultimo_movimento < dia) {
      setDia(dados.ultimo_movimento);
    }
  }, [dados, primeiraCarga, dia]);

  const contas = dados?.contas || [];

  const lancamentos = useMemo(() => {
    if (!dados) return [];
    const vistos = new Set();
    const termo = busca.trim().toLowerCase();
    return dados.lancamentos.filter((l) => {
      if (contaFiltro && l.conta_id !== contaFiltro) return false;
      // Transferencia aparece uma vez so (pela saida) quando as duas pontas estao na lista.
      if (l.transferencia && !contaFiltro) {
        if (vistos.has(l.transferencia)) return false;
        const temPar = dados.lancamentos.some((o) => o.transferencia === l.transferencia && o.id !== l.id);
        if (temPar && l.tipo === "entrada") {
          const saida = dados.lancamentos.find((o) => o.transferencia === l.transferencia && o.tipo === "saida");
          if (saida) return false;
        }
        vistos.add(l.transferencia);
      }
      const tipo = l.transferencia ? "transferencia" : l.tipo;
      if (filtroTipo !== "todos" && filtroTipo !== tipo) return false;
      if (termo && !`${l.descricao} ${l.conta} ${l.contraparte} ${formaInfo(l.forma).rotulo}`.toLowerCase().includes(termo)) return false;
      return true;
    });
  }, [dados, contaFiltro, filtroTipo, busca]);

  const porDia = useMemo(() => {
    const grupos = [];
    for (const l of lancamentos) {
      let grupo = grupos.find((g) => g.data === l.data);
      if (!grupo) {
        grupo = { data: l.data, itens: [], liquido: 0 };
        grupos.push(grupo);
      }
      grupo.itens.push(l);
      if (!l.transferencia) grupo.liquido += l.tipo === "entrada" ? l.valor : -l.valor;
    }
    return grupos;
  }, [lancamentos]);

  const passo = periodo === "mes" ? null : periodo === "semana" ? 7 : 1;
  function andar(direcao) {
    if (passo) return setDia(somarDias(dia, direcao * passo));
    const data = dataDe(dia);
    setDia(isoDe(new Date(data.getFullYear(), data.getMonth() + direcao, 1)));
  }

  async function lancar(payload) {
    await api.criarLancamento(payload);
    if (payload.data < inicio || payload.data > fim) setDia(payload.data);
    await carregar();
  }

  if (carregando && !dados) {
    return <div className="ops-page"><Aviso>Carregando o caixa...</Aviso></div>;
  }

  const totais = dados?.totais;
  const variacao = totais ? totais.fechamento - totais.abertura : 0;
  const contaSelecionada = contas.find((c) => c.id === contaFiltro);

  return (
    <div className="ops-page fin-pagina">
      <div className="fin-barra">
        <div className="fin-segmentado" role="tablist" aria-label="Período">
          {PERIODOS.map((p) => (
            <button key={p.valor} type="button" role="tab" aria-selected={periodo === p.valor} className={periodo === p.valor ? "ativo" : ""} onClick={() => setPeriodo(p.valor)}>
              {p.rotulo}
            </button>
          ))}
        </div>
        <div className="fin-nav-periodo">
          <button type="button" className="icon-btn" aria-label="Anterior" onClick={() => andar(-1)}><Icon name="chevron" size={16} className="fin-seta-esquerda" /></button>
          <strong>{rotuloPeriodo(periodo, dia)}</strong>
          <button type="button" className="icon-btn" aria-label="Próximo" onClick={() => andar(1)}><Icon name="chevron" size={16} /></button>
        </div>
        {dia !== hojeIso() && <button type="button" className="btn-ghost" onClick={() => setDia(hojeIso())}>Hoje</button>}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={() => setModal("extrato")} disabled={!contas.length}><Icon name="file" size={15} /> Importar extrato</button>
        <button type="button" className="btn-secondary" onClick={() => setModal("planilha")}><Icon name="upload" size={15} /> Importar planilha</button>
      </div>

      {erro && <Aviso tipo="error">{erro}</Aviso>}

      {dados && contas.length === 0 ? (
        <PrimeiraConta aoImportar={() => setModal("planilha")} aoCriar={async (c) => { await api.criarConta(c); await carregar(); }} />
      ) : dados && (
        <>
          <section className="card fin-hero">
            <div className="fin-hero-saldo">
              <span className="eyebrow">SALDO EM CONTA · {periodo === "dia" ? `FIM DO DIA ${diaBr(fim)}` : `ATÉ ${diaBr(fim)}`}</span>
              <Dinheiro valor={totais.fechamento} tamanho="xl" />
              <p className="fin-hero-linha">
                Abriu com <b>{brl(totais.abertura)}</b>
                {Math.abs(variacao) >= 0.01 && <span className={`fin-chip ${variacao > 0 ? "entrada" : "saida"}`}>{brl(variacao, { sinal: true })}</span>}
              </p>
              <dl className="fin-hero-numeros">
                <div><dt>Entrou</dt><dd className="entrada">{brl(totais.entradas_externas)}</dd></div>
                <div><dt>Saiu</dt><dd className="saida">{brl(totais.saidas_externas)}</dd></div>
                <div><dt>Entre contas</dt><dd>{brl(totais.transferencias)}</dd></div>
              </dl>
              <Distribuicao contas={contas} />
            </div>
            <GraficoSaldo serie={dados.serie} />
          </section>

          <section className="fin-bancos" aria-label="Bancos">
            {contas.map((c) => (
              <CartaoBanco key={c.id} conta={c} ativo={contaFiltro === c.id} aoClicar={() => setContaFiltro(contaFiltro === c.id ? null : c.id)} />
            ))}
          </section>

          <div className="fin-caixa-grade">
            <section className="card fin-extrato">
              <header className="fin-extrato-topo">
                <div>
                  <h3>Movimentações{contaSelecionada ? ` · ${contaSelecionada.nome}` : ""}</h3>
                  <p>{lancamentos.length} {lancamentos.length === 1 ? "lançamento" : "lançamentos"}{contaSelecionada && <button type="button" className="fin-link" onClick={() => setContaFiltro(null)}>ver todos os bancos</button>}</p>
                </div>
                <div className="fin-extrato-filtros">
                  <div className="fin-segmentado pequeno">
                    {[["todos", "Tudo"], ["entrada", "Entradas"], ["saida", "Saídas"], ["transferencia", "Entre contas"]].map(([v, r]) => (
                      <button key={v} type="button" className={filtroTipo === v ? "ativo" : ""} onClick={() => setFiltroTipo(v)}>{r}</button>
                    ))}
                  </div>
                  <label className="fin-busca">
                    <Icon name="search" size={14} />
                    <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar" aria-label="Buscar lançamento" />
                  </label>
                </div>
              </header>
              {porDia.length === 0 ? (
                <div className="fin-sem-itens">
                  <Icon name="wallet" size={22} />
                  <p>Nenhuma movimentação {periodo === "dia" ? "nesse dia" : "nesse período"}.</p>
                </div>
              ) : porDia.map((grupo) => (
                <div key={grupo.data} className="fin-dia">
                  <h4><span>{diaPorExtenso(grupo.data)}</span><Dinheiro valor={grupo.liquido} sinal tamanho="xs" /></h4>
                  <ul>
                    {grupo.itens.map((item) => (
                      <LinhaLancamento key={item.id} item={item} aberto={abertoId === item.id} aoAbrir={() => setAbertoId(abertoId === item.id ? null : item.id)}>
                        <EditorLancamento
                          lancamento={item}
                          contas={contas}
                          aoCancelar={() => setAbertoId(null)}
                          aoSalvar={async (mudancas) => { await api.atualizarLancamento(item.id, mudancas); setAbertoId(null); await carregar(); }}
                          aoExcluir={async () => { await api.excluirLancamento(item.id); setAbertoId(null); await carregar(); }}
                        />
                      </LinhaLancamento>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
            <NovoLancamento contas={contas} diaPadrao={periodo === "dia" ? dia : hojeIso()} aoLancar={lancar} />
          </div>
        </>
      )}

      {modal === "planilha" && <ImportarPlanilha aoFechar={() => setModal(null)} aoImportar={(r) => { if (r.tipo === "fluxo_caixa") { setPeriodo("dia"); setDia(r.data); } carregar(); }} />}
      {modal === "extrato" && <ImportarExtrato contas={contas} aoFechar={() => setModal(null)} aoImportar={carregar} />}
    </div>
  );
}
