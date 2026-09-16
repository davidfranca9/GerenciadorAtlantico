import { useState } from "react";
import { Link } from "react-router-dom";
import { financeiro as api } from "../../api/client";
import Icon from "../../components/Icon";
import { Aviso, CampoValor, Dinheiro } from "./comum";
import { brl, competenciaDe, diaCurto, hojeIso, numeroBr, toneladas, valorParaCampo } from "./formato";

const PARTES = [
  { chave: "frete_motorista", rotulo: "Motorista" },
  { chave: "agenciamento", rotulo: "Agenciamento" },
  { chave: "comissao", rotulo: "Comissão" },
];

// Margem por tonelada: a media da planilha em setembro foi R$ 50/t.
export function saudeMargem(porTonelada) {
  if (porTonelada === null || porTonelada === undefined) return "neutra";
  if (porTonelada >= 60) return "boa";
  if (porTonelada >= 40) return "media";
  return "baixa";
}

function Medidor({ percentual }) {
  const p = Math.max(0, Math.min(100, percentual || 0));
  const raio = 70;
  const comprimento = Math.PI * raio;
  return (
    <svg className="fin-medidor" viewBox="0 0 180 104" role="img" aria-label={`${p.toLocaleString("pt-BR")}% da meta`}>
      <path d="M20 94 A70 70 0 0 1 160 94" className="fin-medidor-trilho" />
      <path d="M20 94 A70 70 0 0 1 160 94" className="fin-medidor-valor" style={{ strokeDasharray: comprimento, strokeDashoffset: comprimento * (1 - p / 100) }} />
    </svg>
  );
}

function CartaoMeta({ competencia, resumo, meta, aoSalvarMeta }) {
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState("");
  const noMesAtual = competencia === competenciaDe(hojeIso());

  async function salvar(e) {
    e.preventDefault();
    const numero = numeroBr(valor);
    if (numero === null || numero < 0) return;
    await aoSalvarMeta(numero);
    setEditando(false);
  }

  return (
    <section className="card fin-kpi fin-meta">
      <header>
        <span className="eyebrow">META DO MÊS</span>
        {!editando && (
          <button type="button" className="icon-btn" aria-label="Mudar a meta" title="Mudar a meta" onClick={() => { setValor(valorParaCampo(meta.toneladas)); setEditando(true); }}>
            <Icon name="edit" size={14} />
          </button>
        )}
      </header>
      {editando ? (
        <form className="fin-meta-form" onSubmit={salvar}>
          <label className="field"><span>Toneladas no mês</span><input inputMode="decimal" value={valor} autoFocus onChange={(e) => setValor(e.target.value)} /></label>
          <div><button type="button" className="btn-ghost" onClick={() => setEditando(false)}>Cancelar</button><button type="submit" className="btn-primary">Salvar</button></div>
        </form>
      ) : meta.toneladas ? (
        <>
          <div className="fin-meta-medidor">
            <Medidor percentual={meta.percentual} />
            <div>
              <strong>{toneladas(resumo.toneladas)}</strong>
              <span>de {toneladas(meta.toneladas, 0)} · {(meta.percentual || 0).toLocaleString("pt-BR")}%</span>
            </div>
          </div>
          <p className="fin-kpi-rodape">
            {meta.falta > 0 ? (
              <>Faltam <b>{toneladas(meta.falta)}</b>{noMesAtual && meta.dias_restantes > 0 && <> · {meta.dias_restantes} dias de carregamento · <b>{toneladas(meta.ritmo_necessario)}/dia</b></>}</>
            ) : (
              <b className="entrada">Meta batida</b>
            )}
          </p>
        </>
      ) : (
        <div className="fin-meta-vazia">
          <p>Sem meta para este mês.</p>
          <button type="button" className="btn-secondary" onClick={() => { setValor(""); setEditando(true); }}>Definir meta</button>
        </div>
      )}
    </section>
  );
}

function CartaoLucro({ resumo }) {
  return (
    <section className="card fin-kpi">
      <header><span className="eyebrow">LUCRO BRUTO</span></header>
      <Dinheiro valor={resumo.lucro_bruto} tamanho="l" />
      <p className="fin-kpi-destaque">
        {resumo.lucro_por_tonelada !== null ? <><b>{brl(resumo.lucro_por_tonelada)}</b> por tonelada</> : "Sem carregamentos no mês"}
      </p>
      <p className="fin-kpi-rodape">
        {resumo.carregamentos} {resumo.carregamentos === 1 ? "carregamento" : "carregamentos"} · {toneladas(resumo.toneladas)}
        {resumo.cancelados > 0 && ` · ${resumo.cancelados} cancelado${resumo.cancelados > 1 ? "s" : ""}`}
        {" · "}<Link className="fin-link" to="/financeiro/carregamentos">ver cada carga</Link>
      </p>
    </section>
  );
}

function CartaoCustoFixo({ precificacao, resumo }) {
  const custo = precificacao.por_tonelada_atual;
  const margem = resumo.lucro_por_tonelada;
  const cobre = custo !== null && margem !== null ? margem >= custo : null;
  const maior = Math.max(custo || 0, margem || 0) || 1;
  return (
    <section className={`card fin-kpi fin-custo ${cobre === false ? "alerta" : ""}`}>
      <header><span className="eyebrow">CUSTO FIXO POR TONELADA</span></header>
      {custo === null ? (
        <p className="fin-kpi-destaque">Custos fixos de {brl(precificacao.custo_fixo)} no mês. Sem toneladas ainda para dividir.</p>
      ) : (
        <>
          <div className="fin-comparar">
            <div><span>Custo fixo</span><i style={{ width: `${(custo / maior) * 100}%` }} className="custo" /><b>{brl(custo)}/t</b></div>
            <div><span>Lucro médio</span><i style={{ width: `${((margem || 0) / maior) * 100}%` }} className="lucro" /><b>{brl(margem)}/t</b></div>
          </div>
          <p className="fin-kpi-rodape">
            {precificacao.ponto_de_equilibrio_ton !== null && <>Paga os {brl(precificacao.custo_fixo, { centavos: false })} fixos com <b>{toneladas(precificacao.ponto_de_equilibrio_ton, 0)}</b> no mês</>}
            {precificacao.por_tonelada_na_meta !== null && <> · na meta, {brl(precificacao.por_tonelada_na_meta)}/t</>}
          </p>
        </>
      )}
    </section>
  );
}

// Duas leituras simples no lugar da cascata com o zero no meio (que parecia
// quebrada): pra onde foi cada real do frete, e a conta do mes ate a sobra,
// com toda barra saindo da esquerda.
function CaminhoDoFrete({ resumo, despesas, lucroReal, sobra }) {
  const custos = resumo.frete_motorista + resumo.agenciamento + resumo.comissao;
  const partes = [
    { chave: "motorista", rotulo: "Motoristas", valor: resumo.frete_motorista },
    { chave: "agenciamento", rotulo: "Agenciamento", valor: resumo.agenciamento },
    { chave: "comissao", rotulo: "Comissão", valor: resumo.comissao },
    { chave: "sobra", rotulo: "Lucro bruto", valor: resumo.lucro_bruto },
  ];
  // Se os custos passarem do frete, a barra mede os custos e o lucro some dela.
  const base = Math.max(resumo.frete_empresa, custos) || 1;
  const conta = [
    { rotulo: "Lucro bruto dos carregamentos", valor: resumo.lucro_bruto, tipo: "item" },
    { rotulo: "Despesas da empresa", valor: -despesas.empresa, tipo: "item" },
    { rotulo: "Lucro real", valor: lucroReal, tipo: "total" },
    { rotulo: "Gastos pessoais", valor: -despesas.pessoal, tipo: "item" },
    { rotulo: "Sobra do mês", valor: sobra, tipo: "final" },
  ];
  const maior = Math.max(1, ...conta.map((l) => Math.abs(l.valor)));

  return (
    <section className="card fin-caminho">
      <div className="fin-caminho-frete">
        <header>
          <h3>Para onde foi o frete</h3>
          <p>{brl(resumo.frete_empresa)} cobrados em {toneladas(resumo.toneladas)}</p>
        </header>
        <div className="fin-caminho-barra" role="img" aria-label="Divisão do frete cobrado">
          {partes.map((p) => p.valor > 0 && (
            <i key={p.chave} className={p.chave} style={{ width: `${(p.valor / base) * 100}%` }} title={`${p.rotulo}: ${brl(p.valor)}`} />
          ))}
        </div>
        <ul className="fin-caminho-legenda">
          {partes.map((p) => (
            <li key={p.chave} className={p.valor < 0 ? "negativo" : ""}>
              <i className={p.chave} />
              <span>{p.rotulo}</span>
              <Dinheiro valor={p.valor} tamanho="xs" />
              <small>{resumo.frete_empresa ? `${Math.round((p.valor / resumo.frete_empresa) * 100)}%` : ""}</small>
            </li>
          ))}
        </ul>
      </div>
      <div className="fin-caminho-conta">
        <header>
          <h3>O que sobrou no mês</h3>
          <p>Lucro dos carregamentos menos as contas do mês</p>
        </header>
        <ol>
          {conta.map((l) => (
            <li key={l.rotulo} className={`${l.tipo} ${l.valor < 0 ? "negativo" : "positivo"}`}>
              <span className="fin-caminho-rotulo">{l.rotulo}</span>
              <span className="fin-caminho-trilho"><i style={{ width: `${(Math.abs(l.valor) / maior) * 100}%` }} /></span>
              <Dinheiro valor={l.valor} sinal tamanho={l.tipo === "final" ? "m" : "xs"} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const VAZIO = {
  ctes: "", data_emissao: "", motorista: "", fabrica: "Fertimaxi", destino: "", contratante: "", peso: "",
  frete_empresa: { modo: "ton", valor: "" }, frete_motorista: { modo: "ton", valor: "" },
  agenciamento: { modo: "ton", valor: "" }, comissao: { modo: "ton", valor: "" }, cancelado: false, observacao: "",
};

function paraFormulario(c) {
  if (!c) return VAZIO;
  const parte = (chave) => (c[`${chave}_fechado`] !== null && c[`${chave}_fechado`] !== undefined
    ? { modo: "total", valor: valorParaCampo(c[`${chave}_fechado`]) }
    : { modo: "ton", valor: valorParaCampo(c[`${chave}_ton`]) });
  return {
    ctes: c.ctes, data_emissao: c.data_emissao || "", motorista: c.motorista, fabrica: c.fabrica, destino: c.destino,
    contratante: c.contratante, peso: valorParaCampo(c.peso), frete_empresa: parte("frete_empresa"),
    frete_motorista: parte("frete_motorista"), agenciamento: parte("agenciamento"), comissao: parte("comissao"),
    cancelado: c.cancelado, observacao: c.observacao || "",
  };
}

function totalDaParte(parte, peso) {
  const numero = numeroBr(parte.valor) || 0;
  return parte.modo === "total" ? numero : numero * (peso || 0);
}

export function EditorCarregamento({ competencia, carregamento, aoSalvar, aoExcluir, aoFechar }) {
  const [form, setForm] = useState(() => paraFormulario(carregamento));
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [confirmar, setConfirmar] = useState(false);
  const peso = numeroBr(form.peso) || 0;
  const receita = totalDaParte(form.frete_empresa, peso);
  const custos = PARTES.reduce((soma, p) => soma + totalDaParte(form[p.chave], peso), 0);
  const liquido = receita - custos;

  const mudar = (campo, valor) => setForm((f) => ({ ...f, [campo]: valor }));
  const mudarParte = (chave, mudanca) => setForm((f) => ({ ...f, [chave]: { ...f[chave], ...mudanca } }));

  async function salvar(e) {
    e.preventDefault();
    setErro("");
    setSalvando(true);
    const payload = {
      competencia, ctes: form.ctes.trim(), data_emissao: form.data_emissao || null, motorista: form.motorista.trim().toUpperCase(),
      fabrica: form.fabrica.trim(), destino: form.destino.trim(), contratante: form.contratante.trim(), peso,
      cancelado: form.cancelado, observacao: form.observacao,
    };
    for (const chave of ["frete_empresa", ...PARTES.map((p) => p.chave)]) {
      const numero = numeroBr(form[chave].valor);
      payload[`${chave}_ton`] = form[chave].modo === "ton" ? numero : null;
      payload[`${chave}_total`] = form[chave].modo === "total" ? numero : null;
    }
    try {
      await aoSalvar(payload);
    } catch (err) {
      setErro(err.message);
    } finally {
      setSalvando(false);
    }
  }

  const campoParte = (chave, rotulo) => (
    <div className="fin-parte" key={chave}>
      <div className="fin-parte-topo">
        <span>{rotulo}</span>
        <div className="fin-segmentado mini">
          <button type="button" className={form[chave].modo === "ton" ? "ativo" : ""} onClick={() => mudarParte(chave, { modo: "ton" })}>por t</button>
          <button type="button" className={form[chave].modo === "total" ? "ativo" : ""} onClick={() => mudarParte(chave, { modo: "total" })}>total</button>
        </div>
      </div>
      <CampoValor valor={form[chave].valor} aoMudar={(v) => mudarParte(chave, { valor: v })} />
      <small>{form[chave].modo === "ton" ? `= ${brl(totalDaParte(form[chave], peso))}` : peso ? `= ${brl(totalDaParte(form[chave], peso) / peso)}/t` : ""}</small>
    </div>
  );

  return (
    <form className="fin-editor-carregamento" onSubmit={salvar}>
      <div className="fin-editor-grade">
        <label className="field"><span>CT-e</span><input value={form.ctes} onChange={(e) => mudar("ctes", e.target.value)} placeholder="5003 ou 5005/5006" /></label>
        <label className="field"><span>Emissão</span><input type="date" value={form.data_emissao} onChange={(e) => mudar("data_emissao", e.target.value)} /></label>
        <label className="field fin-editor-largo"><span>Motorista</span><input value={form.motorista} onChange={(e) => mudar("motorista", e.target.value)} /></label>
        <label className="field"><span>Fábrica</span>
          <input list="fin-fabricas" value={form.fabrica} onChange={(e) => mudar("fabrica", e.target.value)} />
          <datalist id="fin-fabricas"><option value="Fertimaxi" /><option value="Heringer" /></datalist>
        </label>
        <label className="field"><span>Destino</span><input value={form.destino} onChange={(e) => mudar("destino", e.target.value)} placeholder="Cidade UF" /></label>
        <label className="field"><span>Contratante</span><input value={form.contratante} onChange={(e) => mudar("contratante", e.target.value)} /></label>
        <label className="field"><span>Peso (t)</span><input inputMode="decimal" value={form.peso} onChange={(e) => mudar("peso", e.target.value)} /></label>
      </div>
      <div className="fin-partes">
        {campoParte("frete_empresa", "Frete cobrado")}
        {PARTES.map((p) => campoParte(p.chave, p.rotulo))}
      </div>
      <div className="fin-editor-resultado">
        <span>Sobra desta carga</span>
        <Dinheiro valor={liquido} tamanho="m" />
        {peso > 0 && <b className={`fin-margem ${saudeMargem(liquido / peso)}`}>{brl(liquido / peso)}/t</b>}
        <label className="fin-check"><input type="checkbox" checked={form.cancelado} onChange={(e) => mudar("cancelado", e.target.checked)} /> Cancelado</label>
      </div>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-editor-acoes">
        {carregamento && (confirmar ? (
          <span className="fin-confirmar">Apagar este carregamento?
            <button type="button" className="btn-ghost perigo" onClick={aoExcluir}>Apagar</button>
            <button type="button" className="btn-ghost" onClick={() => setConfirmar(false)}>Não</button>
          </span>
        ) : <button type="button" className="btn-ghost perigo" onClick={() => setConfirmar(true)}><Icon name="trash" size={14} /> Excluir</button>)}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoFechar}>Cancelar</button>
        <button type="submit" className="btn-primary" disabled={salvando}>{salvando ? "Salvando..." : "Salvar"}</button>
      </div>
    </form>
  );
}

// A barra fina mostra pra onde foi cada real do frete: motorista,
// agenciamento, comissao e o que sobrou.
export function Composicao({ totais }) {
  const receita = totais.frete_empresa;
  if (!receita) return null;
  const pedacos = [
    ["motorista", totais.frete_motorista],
    ["agenciamento", totais.agenciamento],
    ["comissao", totais.comissao],
    ["sobra", Math.max(0, totais.liquido)],
  ];
  return (
    <span className="fin-composicao" title={`Motorista ${brl(totais.frete_motorista)} · Agenciamento ${brl(totais.agenciamento)} · Comissão ${brl(totais.comissao)} · Sobra ${brl(totais.liquido)}`}>
      {pedacos.map(([nome, valor]) => valor > 0 && <i key={nome} className={nome} style={{ width: `${(valor / receita) * 100}%` }} />)}
    </span>
  );
}

function Ranking({ titulo, grupos }) {
  const maior = Math.max(1, ...grupos.map((g) => Math.abs(g.lucro)));
  return (
    <section className="card fin-ranking">
      <header><h3>{titulo}</h3><p>Sobra do mês e média por tonelada</p></header>
      {grupos.length === 0 ? <p className="fin-sem-itens">Sem carregamentos.</p> : (
        <ol>
          {grupos.map((g) => (
            <li key={g.nome}>
              <div className="fin-ranking-topo"><strong>{g.nome}</strong><Dinheiro valor={g.lucro} tamanho="xs" /></div>
              <span className="fin-ranking-barra"><i style={{ width: `${(Math.abs(g.lucro) / maior) * 100}%` }} /></span>
              <small>{g.carregamentos} {g.carregamentos === 1 ? "carga" : "cargas"} · {toneladas(g.toneladas)} · <b className={`fin-margem ${saudeMargem(g.por_tonelada)}`}>{brl(g.por_tonelada)}/t</b></small>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

// Pagina "Lucro bruto": o resumo do mes. Cada carga fica em "Carregamentos".
export function AbaLucroBruto({ competencia, dados, recarregar }) {
  const vazio = dados.carregamentos.length === 0;
  return (
    <>
      <div className="fin-kpis">
        <CartaoMeta competencia={competencia} resumo={dados.resumo} meta={dados.meta} aoSalvarMeta={async (t) => { await api.definirMeta(competencia, t); await recarregar(); }} />
        <CartaoLucro resumo={dados.resumo} />
        <CartaoCustoFixo precificacao={dados.precificacao} resumo={dados.resumo} />
      </div>

      {vazio ? (
        <section className="card fin-sem-itens">
          <Icon name="truck" size={22} />
          <p>Nenhum carregamento em {competencia.split("-").reverse().join("/")}. Importe a planilha do Controle de Carregamentos ou lance as cargas em <Link className="fin-link" to="/financeiro/carregamentos">Carregamentos</Link>.</p>
        </section>
      ) : (
        <>
          <CaminhoDoFrete resumo={dados.resumo} despesas={dados.despesas} lucroReal={dados.lucro_real} sobra={dados.sobra} />
          <div className="fin-rankings">
            <Ranking titulo="Por contratante" grupos={dados.por_contratante} />
            <Ranking titulo="Por fábrica" grupos={dados.por_fabrica} />
          </div>
        </>
      )}
    </>
  );
}
