import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { financeiro as api } from "../../api/client";
import Icon from "../../components/Icon";
import { Aviso, CampoValor, Dinheiro, Modal, usePodeGravar } from "./comum";
import { brl, brlCurto, competenciaDe, diaBr, diaPorExtenso, diasAte, hojeIso, isoDe, numeroBr, valorParaCampo } from "./formato";

const SITUACAO = {
  pago: { rotulo: "Pago", classe: "pago" },
  atrasado: { rotulo: "Atrasado", classe: "atrasado" },
  hoje: { rotulo: "Vence hoje", classe: "hoje" },
  a_vencer: { rotulo: "A vencer", classe: "a-vencer" },
  sem_data: { rotulo: "Sem dia", classe: "sem-data" },
};

function Resumo({ totais }) {
  const pagoPct = totais.total ? Math.round((totais.pago / totais.total) * 100) : 0;
  return (
    <section className="fin-resumo-contas">
      <div className="card">
        <span className="eyebrow">A PAGAR NO MÊS</span>
        <Dinheiro valor={totais.a_pagar} tamanho="l" />
        <span className="fin-progresso" aria-label={`${pagoPct}% pago`}><i style={{ width: `${pagoPct}%` }} /></span>
        <small>{brl(totais.pago)} pagos de {brl(totais.total)} · {pagoPct}%</small>
      </div>
      <div className={`card ${totais.atrasado > 0 ? "alerta" : ""}`}>
        <span className="eyebrow">ATRASADO</span>
        <Dinheiro valor={totais.atrasado} tamanho="l" />
        <small>{totais.atrasados ? `${totais.atrasados} ${totais.atrasados === 1 ? "conta" : "contas"}` : "Nada vencido"}</small>
      </div>
      <div className="card">
        <span className="eyebrow">PRÓXIMOS 7 DIAS</span>
        <Dinheiro valor={totais.proximos_7_dias} tamanho="l" />
        <small>{totais.sem_valor ? `${totais.sem_valor} sem valor definido` : "Contando a partir de hoje"}</small>
      </div>
    </section>
  );
}

function Calendario({ competencia, itens, hoje, selecionado, aoSelecionar }) {
  const [ano, mes] = competencia.split("-").map(Number);
  const primeiro = new Date(ano, mes - 1, 1);
  const ultimoDia = new Date(ano, mes, 0).getDate();
  const porDia = useMemo(() => {
    const mapa = {};
    for (const item of itens) {
      if (!item.vencimento) continue;
      (mapa[item.vencimento] ||= []).push(item);
    }
    return mapa;
  }, [itens]);

  const dias = Array((primeiro.getDay() + 6) % 7).fill(null);
  for (let d = 1; d <= ultimoDia; d += 1) dias.push(isoDe(new Date(ano, mes - 1, d)));
  while (dias.length % 7) dias.push(null);
  const semanas = [];
  for (let i = 0; i < dias.length; i += 7) semanas.push(dias.slice(i, i + 7));
  const valor = (i) => i.pagamento?.valor ?? i.valor ?? 0;

  return (
    <div className="fin-calendario">
      {["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom", "Semana"].map((d) => <span key={d} className="fin-cal-semana">{d}</span>)}
      {semanas.map((semana, n) => {
        const daSemana = semana.flatMap((iso) => (iso ? porDia[iso] || [] : []));
        const total = daSemana.reduce((s, i) => s + valor(i), 0);
        const falta = daSemana.filter((i) => i.situacao !== "pago").reduce((s, i) => s + valor(i), 0);
        return (
          <Fragment key={n}>
            {semana.map((iso, i) => {
              if (!iso) return <span key={`v${n}-${i}`} className="fin-cal-vazio" />;
              const doDia = porDia[iso] || [];
              const aberto = doDia.filter((item) => item.situacao !== "pago");
              const totalDia = aberto.reduce((soma, item) => soma + (item.valor || 0), 0);
              const estado = doDia.length === 0 ? "" : aberto.length === 0 ? "quitado" : aberto.some((item) => item.situacao === "atrasado") ? "atrasado" : "aberto";
              return (
                <button
                  key={iso}
                  type="button"
                  className={`fin-cal-dia ${estado} ${iso === hoje ? "hoje" : ""} ${iso === selecionado ? "selecionado" : ""}`}
                  onClick={() => aoSelecionar(iso)}
                  aria-label={`${diaPorExtenso(iso)}: ${doDia.length} contas`}
                >
                  <span className="fin-cal-numero">{Number(iso.slice(8))}</span>
                  {doDia.length > 0 && (
                    <>
                      <span className="fin-cal-total">{aberto.length ? (totalDia ? brlCurto(totalDia) : "a definir") : <Icon name="check" size={13} />}</span>
                      <span className="fin-cal-pontos">{doDia.slice(0, 5).map((item) => <i key={`${item.origem}${item.id}`} className={SITUACAO[item.situacao].classe} />)}</span>
                    </>
                  )}
                </button>
              );
            })}
            <span className={`fin-cal-semana-total ${total && !falta ? "quitada" : ""}`} title={total ? `Semana: ${brl(total)}${falta ? ` · a pagar ${brl(falta)}` : " · tudo pago"}` : "Nada na semana"}>
              {total ? (
                <>
                  <b>{brlCurto(total)}</b>
                  <small>{falta ? (falta < total ? `falta ${brlCurto(falta)}` : "a pagar") : "pago"}</small>
                </>
              ) : "—"}
            </span>
          </Fragment>
        );
      })}
    </div>
  );
}

function FormPagar({ item, contas, competencia, aoPagar, aoCancelar }) {
  const [contaId, setContaId] = useState(contas[0]?.id ? String(contas[0].id) : "");
  const [data, setData] = useState(hojeIso() < (item.vencimento || "") ? hojeIso() : item.vencimento || hojeIso());
  const [valor, setValor] = useState(valorParaCampo(item.valor));
  const [erro, setErro] = useState("");

  async function pagar(e) {
    e.preventDefault();
    const numero = numeroBr(valor);
    if (!numero) return setErro("Informe o valor pago");
    try {
      await aoPagar({ origem: item.origem, origem_id: item.id, competencia, pago_em: data, valor: numero, conta_id: contaId ? Number(contaId) : null });
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="fin-pagar" onSubmit={pagar}>
      <label className="field"><span>Valor pago</span><CampoValor valor={valor} aoMudar={setValor} autoFocus /></label>
      <label className="field"><span>Pago em</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></label>
      <label className="field"><span>Saiu de</span>
        <select value={contaId} onChange={(e) => setContaId(e.target.value)}>
          {contas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          <option value="">Não lançar no caixa</option>
        </select>
      </label>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-editor-acoes">
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary"><Icon name="check" size={14} /> Confirmar pagamento</button>
      </div>
    </form>
  );
}

function ItemAgenda({ item, contas, competencia, grupos, despesaDe, aoPagar, aoDesfazer, aoEditar, aoExcluir }) {
  const [pagando, setPagando] = useState(false);
  const [editando, setEditando] = useState(false);
  const podeGravar = usePodeGravar();
  const situacao = SITUACAO[item.situacao];
  const fixa = item.origem === "despesa";
  const despesa = fixa ? despesaDe(item) : null;
  return (
    <li className={`fin-conta ${situacao.classe}`}>
      <div className="fin-conta-linha">
        <span className="fin-conta-texto">
          <strong>{item.descricao}{item.parcela && <em>{item.parcela}</em>}</strong>
          <small>
            <span className={`fin-tipo ${fixa ? "fixa" : "avulsa"}`}>{fixa ? "Fixa" : "Avulsa"}</span>
            <span className={`fin-escopo ${item.escopo}`}>{item.escopo === "empresa" ? "Empresa" : "Pessoal"}</span>
            {fixa ? item.grupo : ""}
            {item.pagamento && ` · pago em ${diaBr(item.pagamento.pago_em)}${item.pagamento.conta ? ` pelo ${item.pagamento.conta}` : ""}`}
          </small>
        </span>
        <span className="fin-conta-valor">
          {item.valor === null && !item.pagamento ? <em>valor a definir</em> : <Dinheiro valor={item.pagamento ? item.pagamento.valor : item.valor} tamanho="s" />}
          <b className={`fin-situacao ${situacao.classe}`}>{situacao.rotulo}</b>
        </span>
        {/* Pagar, desfazer, editar e excluir sao gravacao: quem so visualiza ve
            a conta, o valor e a situacao (pago, atrasado, a vencer) sem acao. */}
        {podeGravar && <span className="fin-conta-acoes">
          {item.pagamento ? (
            <button type="button" className="btn-ghost" onClick={() => aoDesfazer(item)} title="Desfazer pagamento">Desfazer</button>
          ) : (
            <button type="button" className="btn-secondary" onClick={() => setPagando(!pagando)}>{pagando ? "Fechar" : "Pagar"}</button>
          )}
          <button
            type="button"
            className={`icon-btn${editando ? " ativo" : ""}`}
            aria-label={`Editar ${item.descricao}`}
            title="Editar ou excluir"
            onClick={() => { setEditando(!editando); setPagando(false); }}
          >
            <Icon name={editando ? "close" : "edit"} size={14} />
          </button>
        </span>}
      </div>
      {pagando && (
        <FormPagar item={item} contas={contas} competencia={competencia} aoCancelar={() => setPagando(false)} aoPagar={async (p) => { await aoPagar(p); setPagando(false); }} />
      )}
      {editando && !fixa && (
        <EditorAvulsa
          item={item}
          aoSalvar={async (dados) => { await aoEditar(item, dados); setEditando(false); }}
          aoExcluir={() => aoExcluir(item)}
          aoCancelar={() => setEditando(false)}
        />
      )}
      {editando && fixa && (despesa ? (
        <EditorDespesa
          escopo={item.escopo}
          competencia={competencia}
          despesa={despesa}
          grupos={grupos}
          aoSalvar={async (dados) => { await aoEditar(item, dados); setEditando(false); }}
          aoExcluir={() => aoExcluir(item)}
          aoCancelar={() => setEditando(false)}
        />
      ) : (
        <Aviso>Carregando a conta fixa...</Aviso>
      ))}
    </li>
  );
}


// Mesma conta avulsa da agenda, agora editavel: o Claus pediu poder corrigir
// e apagar o que foi lancado, sem ter que refazer.
function EditorAvulsa({ item, aoSalvar, aoExcluir, aoCancelar }) {
  const [descricao, setDescricao] = useState(item.descricao);
  const [data, setData] = useState(item.vencimento);
  const [valor, setValor] = useState(item.valor === null ? "" : valorParaCampo(item.valor));
  const [escopo, setEscopo] = useState(item.escopo);
  const [confirmar, setConfirmar] = useState(false);
  const [erro, setErro] = useState("");

  async function salvar(e) {
    e.preventDefault();
    setErro("");
    try {
      await aoSalvar({ descricao: descricao.trim(), data, valor: numeroBr(valor), escopo });
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="fin-avulsa" onSubmit={salvar}>
      <div className="fin-editor-grade">
        <label className="field fin-editor-largo"><span>Descrição</span><input value={descricao} onChange={(e) => setDescricao(e.target.value)} required autoFocus /></label>
        <label className="field"><span>Vence em</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} required /></label>
        <label className="field"><span>Valor</span><CampoValor valor={valor} aoMudar={setValor} placeholder="a definir" /></label>
        <label className="field"><span>De quem</span>
          <select value={escopo} onChange={(e) => setEscopo(e.target.value)}><option value="empresa">Empresa</option><option value="pessoal">Pessoal</option></select>
        </label>
      </div>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-editor-acoes">
        {confirmar ? (
          <span className="fin-confirmar">Apagar esta conta?
            <button type="button" className="btn-ghost perigo" onClick={async () => {
              try { await aoExcluir(); } catch (err) { setErro(err.message); setConfirmar(false); }
            }}>Apagar</button>
            <button type="button" className="btn-ghost" onClick={() => setConfirmar(false)}>Não</button>
          </span>
        ) : <button type="button" className="btn-ghost perigo" onClick={() => setConfirmar(true)}><Icon name="trash" size={14} /> Excluir</button>}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary">Salvar</button>
      </div>
    </form>
  );
}


function Filtro({ rotulo, valor, opcoes, aoMudar }) {
  return (
    <div className="fin-filtro">
      <span>{rotulo}</span>
      <div className="fin-filtro-botoes" role="group" aria-label={rotulo}>
        {opcoes.map(([v, texto]) => (
          <button key={v} type="button" className={valor === v ? "ativo" : ""} aria-pressed={valor === v} onClick={() => aoMudar(v)}>{texto}</button>
        ))}
      </div>
    </div>
  );
}

function NovaAvulsa({ dia, aoCriar, aoCancelar }) {
  const [descricao, setDescricao] = useState("");
  const [data, setData] = useState(dia);
  const [valor, setValor] = useState("");
  const [escopo, setEscopo] = useState("empresa");
  const [erro, setErro] = useState("");

  async function criar(e) {
    e.preventDefault();
    try {
      await aoCriar({ descricao: descricao.trim(), data, valor: numeroBr(valor), escopo });
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="fin-avulsa" onSubmit={criar}>
      <strong>Conta avulsa</strong>
      <small>Posto, cheque, acerto: o que não se repete todo mês.</small>
      <div className="fin-editor-grade">
        <label className="field fin-editor-largo"><span>Descrição</span><input value={descricao} onChange={(e) => setDescricao(e.target.value)} required autoFocus /></label>
        <label className="field"><span>Vence em</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} required /></label>
        <label className="field"><span>Valor</span><CampoValor valor={valor} aoMudar={setValor} placeholder="a definir" /></label>
        <label className="field"><span>De quem</span>
          <select value={escopo} onChange={(e) => setEscopo(e.target.value)}><option value="empresa">Empresa</option><option value="pessoal">Pessoal</option></select>
        </label>
      </div>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-editor-acoes">
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary">Adicionar</button>
      </div>
    </form>
  );
}

const FILTROS_ABERTOS = { tipo: "todas", escopo: "todos", situacao: "todas" };

function Agenda({ competencia, dados, contas, recarregar }) {
  const podeGravar = usePodeGravar();
  const hoje = dados.hoje;
  const [dia, setDia] = useState(null);
  const [novaAvulsa, setNovaAvulsa] = useState(false);
  const [erro, setErro] = useState("");
  const [filtros, setFiltros] = useState(FILTROS_ABERTOS);
  // As contas fixas inteiras, pra poder editar daqui (a agenda so traz o resumo).
  const [despesas, setDespesas] = useState([]);

  useEffect(() => {
    // As despesas inteiras servem so pro editor. Quem nao pode editar nao
    // precisa delas - e a aba de Pagamentos nem le despesa (GET de outra aba).
    if (!podeGravar) return;
    api.despesas(competencia).then(setDespesas).catch(() => setDespesas([]));
  }, [competencia, podeGravar]);

  useEffect(() => {
    // Abre no dia de hoje se ele e do mes; senao, no primeiro dia com conta.
    if (competenciaDe(hoje) === competencia) setDia(hoje);
    else setDia(dados.itens.find((i) => i.vencimento)?.vencimento || `${competencia}-01`);
  }, [competencia]); // eslint-disable-line react-hooks/exhaustive-deps

  const combina = (i) => (
    (filtros.tipo === "todas" || (filtros.tipo === "fixa" ? i.origem === "despesa" : i.origem === "avulsa"))
    && (filtros.escopo === "todos" || i.escopo === filtros.escopo)
    && (filtros.situacao === "todas"
      || (filtros.situacao === "aberto" && !i.pagamento)
      || (filtros.situacao === "atrasado" && i.situacao === "atrasado")
      || (filtros.situacao === "pago" && Boolean(i.pagamento)))
  );
  const itens = dados.itens.filter(combina);
  const filtrando = itens.length !== dados.itens.length;
  const doDia = itens.filter((i) => i.vencimento === dia);
  const semData = itens.filter((i) => !i.vencimento);
  const atrasadas = itens.filter((i) => i.situacao === "atrasado" && i.vencimento !== dia);
  const outrosDias = itens.filter((i) => i.vencimento && i.vencimento !== dia && i.situacao !== "atrasado");
  const grupos = [...new Set(despesas.map((d) => d.grupo).filter(Boolean))];
  const despesaDe = (item) => despesas.find((d) => d.id === item.id) || null;

  async function agir(acao) {
    setErro("");
    try {
      await acao();
      await recarregar();
    } catch (err) {
      setErro(err.message);
    }
  }

  // Estes dois deixam o erro subir de proposito: o editor segura o que foi
  // digitado e mostra a mensagem ali mesmo (ex.: conta ja paga nao se apaga).
  async function salvarItem(item, dados) {
    setErro("");
    await (item.origem === "despesa" ? api.atualizarDespesa(item.id, dados) : api.atualizarAvulsa(item.id, dados));
    await recarregar();
  }

  async function excluirItem(item) {
    setErro("");
    await (item.origem === "despesa" ? api.excluirDespesa(item.id) : api.excluirAvulsa(item.id));
    await recarregar();
  }

  const lista = (itens) => (
    <ul className="fin-contas">
      {itens.map((item) => (
        <ItemAgenda
          key={`${item.origem}-${item.id}`}
          item={item}
          contas={contas}
          competencia={competencia}
          grupos={grupos}
          despesaDe={despesaDe}
          aoPagar={(p) => agir(() => api.pagar(p))}
          aoDesfazer={(i) => agir(() => api.desfazerPagamento({ origem: i.origem, origem_id: i.id, competencia }))}
          aoEditar={salvarItem}
          aoExcluir={excluirItem}
        />
      ))}
    </ul>
  );

  return (
    <div className="fin-agenda">
      <section className="card">
        <div className="fin-filtros">
          <Filtro rotulo="Cobrança" valor={filtros.tipo} aoMudar={(v) => setFiltros({ ...filtros, tipo: v })}
            opcoes={[["todas", "Todas"], ["fixa", "Fixas"], ["avulsa", "Avulsas"]]} />
          <Filtro rotulo="De quem" valor={filtros.escopo} aoMudar={(v) => setFiltros({ ...filtros, escopo: v })}
            opcoes={[["todos", "Todos"], ["empresa", "Empresa"], ["pessoal", "Pessoal"]]} />
          <Filtro rotulo="Situação" valor={filtros.situacao} aoMudar={(v) => setFiltros({ ...filtros, situacao: v })}
            opcoes={[["todas", "Todas"], ["aberto", "Em aberto"], ["atrasado", "Atrasadas"], ["pago", "Pagas"]]} />
          {filtrando && (
            <button type="button" className="btn-ghost fin-filtro-limpar" onClick={() => setFiltros(FILTROS_ABERTOS)}>
              {itens.length} de {dados.itens.length} contas · limpar filtro
            </button>
          )}
        </div>
        <Calendario competencia={competencia} itens={itens} hoje={hoje} selecionado={dia} aoSelecionar={setDia} />
        <div className="fin-cal-legenda">
          <span><i className="atrasado" />Atrasado</span><span><i className="a-vencer" />A vencer</span><span><i className="pago" />Pago</span>
        </div>
      </section>
      <section className="card fin-agenda-dia">
        <header className="fin-extrato-topo">
          <div>
            <h3>{dia ? diaPorExtenso(dia, hoje) : "Escolha um dia"}</h3>
            <p>{doDia.length ? `${doDia.length} ${doDia.length === 1 ? "conta" : "contas"} · ${brl(doDia.reduce((s, i) => s + (i.pagamento?.valor ?? i.valor ?? 0), 0))}` : "Nada vence neste dia"}</p>
          </div>
          {podeGravar && <button type="button" className="btn-secondary" onClick={() => setNovaAvulsa(!novaAvulsa)}><Icon name="plus" size={14} /> Conta avulsa</button>}
        </header>
        {erro && <Aviso tipo="error">{erro}</Aviso>}
        {novaAvulsa && (
          <NovaAvulsa dia={dia || hoje} aoCancelar={() => setNovaAvulsa(false)} aoCriar={async (a) => { await api.criarAvulsa(a); setNovaAvulsa(false); setDia(a.data); await recarregar(); }} />
        )}
        {doDia.length > 0 && lista(doDia)}
        {atrasadas.length > 0 && (
          <details className="fin-secao" open={atrasadas.length <= 5}>
            <summary className="fin-subtitulo alerta">
              Atrasadas em outros dias <b>{atrasadas.length} · {brl(atrasadas.reduce((s, i) => s + (i.valor || 0), 0))}</b>
            </summary>
            {lista(atrasadas)}
          </details>
        )}
        {outrosDias.length > 0 && (
          <details className="fin-secao" open>
            <summary className="fin-subtitulo">
              Outros vencimentos do mês <b>{outrosDias.length} · {brl(outrosDias.reduce((s, i) => s + (i.pagamento?.valor ?? i.valor ?? 0), 0))}</b>
            </summary>
            {lista(outrosDias)}
          </details>
        )}
        {semData.length > 0 && (
          <details className="fin-secao" open>
            <summary className="fin-subtitulo">
              Sem dia de vencimento <b>{semData.length} · {brl(semData.reduce((s, i) => s + (i.pagamento?.valor ?? i.valor ?? 0), 0))}</b>
            </summary>
            {lista(semData)}
          </details>
        )}
      </section>
    </div>
  );
}

const DESPESA_VAZIA = { descricao: "", grupo: "", dia_vencimento: "", valor: "", parcelado: false, parcela_inicial: "", parcelas_total: "", entra_precificacao: false, conta_no_resultado: true, ativa: true };

function EditorDespesa({ escopo, competencia, despesa, grupos, aoSalvar, aoExcluir, aoCancelar }) {
  const [form, setForm] = useState(() => despesa ? {
    descricao: despesa.descricao, grupo: despesa.grupo, dia_vencimento: despesa.dia_vencimento ?? "", valor: valorParaCampo(despesa.valor),
    parcelado: Boolean(despesa.parcelas_total), parcela_inicial: despesa.parcela_inicial ?? "", parcelas_total: despesa.parcelas_total ?? "",
    entra_precificacao: despesa.entra_precificacao, conta_no_resultado: despesa.conta_no_resultado, ativa: despesa.ativa,
  } : { ...DESPESA_VAZIA, grupo: grupos[0] || "" });
  const [erro, setErro] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const mudar = (campo, valor) => setForm((f) => ({ ...f, [campo]: valor }));

  async function salvar(e) {
    e.preventDefault();
    try {
      await aoSalvar({
        escopo, competencia_inicio: despesa?.competencia_inicio || competencia, descricao: form.descricao.trim(), grupo: form.grupo.trim() || "Outras",
        dia_vencimento: form.dia_vencimento === "" ? null : Number(form.dia_vencimento), valor: numeroBr(form.valor) || 0,
        parcela_inicial: form.parcelado ? Number(form.parcela_inicial) || 1 : null, parcelas_total: form.parcelado ? Number(form.parcelas_total) || null : null,
        entra_precificacao: form.entra_precificacao, conta_no_resultado: form.conta_no_resultado, ativa: form.ativa, ordem: despesa?.ordem ?? 500,
      });
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="fin-editor-despesa" onSubmit={salvar}>
      <div className="fin-editor-grade">
        <label className="field fin-editor-largo"><span>Descrição</span><input value={form.descricao} onChange={(e) => mudar("descricao", e.target.value)} required autoFocus /></label>
        <label className="field"><span>Valor</span><CampoValor valor={form.valor} aoMudar={(v) => mudar("valor", v)} /></label>
        <label className="field"><span>Vence dia</span><input type="number" min="1" max="31" value={form.dia_vencimento} onChange={(e) => mudar("dia_vencimento", e.target.value)} placeholder="—" /></label>
        <label className="field"><span>Grupo</span>
          <input list={`fin-grupos-${escopo}`} value={form.grupo} onChange={(e) => mudar("grupo", e.target.value)} />
          <datalist id={`fin-grupos-${escopo}`}>{grupos.map((g) => <option key={g} value={g} />)}</datalist>
        </label>
      </div>
      <div className="fin-checks">
        <label className="fin-check"><input type="checkbox" checked={form.parcelado} onChange={(e) => mudar("parcelado", e.target.checked)} /> Parcelada</label>
        {form.parcelado && (
          <span className="fin-parcelas">
            parcela <input type="number" min="1" value={form.parcela_inicial} onChange={(e) => mudar("parcela_inicial", e.target.value)} aria-label="Parcela deste mês" />
            de <input type="number" min="1" value={form.parcelas_total} onChange={(e) => mudar("parcelas_total", e.target.value)} aria-label="Total de parcelas" />
          </span>
        )}
        {escopo === "empresa" && (
          <>
            <label className="fin-check"><input type="checkbox" checked={form.entra_precificacao} onChange={(e) => mudar("entra_precificacao", e.target.checked)} /> Entra no custo fixo por tonelada</label>
            <label className="fin-check"><input type="checkbox" checked={!form.conta_no_resultado} onChange={(e) => mudar("conta_no_resultado", !e.target.checked)} /> Só na precificação (não é boleto do mês)</label>
          </>
        )}
        <label className="fin-check"><input type="checkbox" checked={!form.ativa} onChange={(e) => mudar("ativa", !e.target.checked)} /> Encerrada</label>
      </div>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-editor-acoes">
        {despesa && (confirmar ? (
          <span className="fin-confirmar">Apagar esta despesa?
            <button type="button" className="btn-ghost perigo" onClick={async () => {
              try { await aoExcluir(); } catch (err) { setErro(err.message); setConfirmar(false); }
            }}>Apagar</button>
            <button type="button" className="btn-ghost" onClick={() => setConfirmar(false)}>Não</button>
          </span>
        ) : <button type="button" className="btn-ghost perigo" onClick={() => setConfirmar(true)}><Icon name="trash" size={14} /> Excluir</button>)}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary">Salvar</button>
      </div>
    </form>
  );
}

export function Despesas({ escopo, competencia, despesas, recarregar, fechamento = [], tarifas = [], dividas = [], pagamentos = [] }) {
  const podeGravar = usePodeGravar();
  // Sem poder gravar, a linha da despesa nao e botao: ela nao abre o editor,
  // mas mostra o mesmo - descricao, parcelas, situacao do mes e valor.
  const LinhaDespesa = podeGravar ? "button" : "div";
  const [aberto, setAberto] = useState(null);
  const minhas = despesas.filter((d) => d.escopo === escopo);
  const grupos = [...new Set([...minhas.map((d) => d.grupo), ...(tarifas.length ? ["Taxas"] : []), ...(dividas.length ? ["Dívidas ativas"] : [])])];
  const doMes = minhas.filter((d) => d.vale_no_mes && d.conta_no_resultado);
  const pagamentoPorDespesa = new Map(pagamentos.filter((p) => p.origem === "despesa").map((p) => [p.id, p]));
  const total = doMes.reduce((s, d) => s + d.valor, 0) + tarifas.reduce((s, d) => s + d.valor, 0) + dividas.reduce((s, d) => s + (d.valor_parcela || 0), 0);

  async function salvar(id, dados) {
    if (id) await api.atualizarDespesa(id, dados);
    else await api.criarDespesa(dados);
    setAberto(null);
    await recarregar();
  }

  return (
    <div className="fin-despesas">
      <div className="fin-despesas-topo">
        <div>
          <span className="eyebrow">{escopo === "empresa" ? "DESPESAS DA EMPRESA" : "GASTOS PESSOAIS"} NO MÊS</span>
          <Dinheiro valor={total} tamanho="l" />
          <small>{doMes.length} contas fixas{tarifas.length ? ` · ${tarifas.length} tarifas do Caixa` : ""}{dividas.length ? ` · ${dividas.length} dívidas ativas` : ""} em {grupos.length} grupos</small>
        </div>
        {fechamento.length > 0 && (
          <dl className="fin-fechamento">
            {fechamento.map((f) => (
              <div key={f.rotulo} className={f.destaque ? "destaque" : ""}>
                <dt>{f.rotulo}</dt>
                <dd><Dinheiro valor={f.valor} tamanho={f.destaque ? "m" : "s"} /></dd>
              </div>
            ))}
          </dl>
        )}
        {podeGravar && <button type="button" className="btn-primary" onClick={() => setAberto(aberto === "nova" ? null : "nova")}><Icon name="plus" size={14} /> Despesa</button>}
        <Link className="btn-secondary" to="/financeiro/pagamentos"><Icon name="calendar" size={14} /> Ver pagamentos</Link>
      </div>
      {aberto === "nova" && (
        <div className="card"><EditorDespesa escopo={escopo} competencia={competencia} grupos={grupos} aoCancelar={() => setAberto(null)} aoSalvar={(d) => salvar(null, d)} /></div>
      )}
      {minhas.length === 0 && aberto !== "nova" && (
        <div className="card fin-sem-itens"><Icon name="calendar" size={22} /><p>Nenhuma despesa {escopo === "empresa" ? "da empresa" : "pessoal"} cadastrada{podeGravar ? ". Importe a planilha do Controle de Carregamentos ou adicione a primeira." : "."}</p></div>
      )}
      <div className="fin-grupos">
        {grupos.map((grupo) => {
          const itens = minhas.filter((d) => d.grupo === grupo);
          const itensTarifa = grupo === "Taxas" ? tarifas : [];
          const itensDivida = grupo === "Dívidas ativas" ? dividas : [];
          const subtotal = itens.filter((d) => d.vale_no_mes && d.conta_no_resultado).reduce((s, d) => s + d.valor, 0) + itensTarifa.reduce((s, d) => s + d.valor, 0) + itensDivida.reduce((s, d) => s + (d.valor_parcela || 0), 0);
          return (
            <section key={grupo} className="card fin-grupo">
              <header><h3>{grupo}</h3><Dinheiro valor={subtotal} tamanho="xs" /></header>
              <ul>
                {itens.map((d) => (
                  <li key={d.id} className={`${!d.vale_no_mes || !d.ativa ? "fora" : ""} ${aberto === d.id ? "aberto" : ""}`}>
                    <LinhaDespesa
                      className={`fin-despesa-linha ${podeGravar ? "" : "so-leitura"}`}
                      {...(podeGravar ? { type: "button", onClick: () => setAberto(aberto === d.id ? null : d.id), "aria-expanded": aberto === d.id } : {})}
                    >
                      <span className="fin-despesa-dia">{d.dia_vencimento ? <>dia<b>{d.dia_vencimento}</b></> : <b>—</b>}</span>
                      <span className="fin-despesa-texto">
                        <strong>{d.descricao}</strong>
                        <small>
                          {d.parcelas_total && (
                            <span className="fin-parcela">
                              <span className="fin-progresso mini"><i style={{ width: `${((d.parcela || d.parcelas_total) / d.parcelas_total) * 100}%` }} /></span>
                              {d.parcela ? `parcela ${d.parcela} de ${d.parcelas_total}` : "parcelas encerradas"}
                            </span>
                          )}
                          {d.entra_precificacao && <span className="fin-tag">{d.conta_no_resultado ? "custo fixo" : "só precificação"}</span>}
                          {!d.ativa && <span className="fin-tag">encerrada</span>}
                          {d.vale_no_mes && d.conta_no_resultado && pagamentoPorDespesa.get(d.id)?.situacao === "pago" && <span className="fin-tag pago">pago</span>}
                          {d.vale_no_mes && d.conta_no_resultado && pagamentoPorDespesa.get(d.id)?.situacao === "atrasado" && <span className="fin-tag atrasado">atrasado</span>}
                          {d.vale_no_mes && d.conta_no_resultado && ["hoje", "a_vencer"].includes(pagamentoPorDespesa.get(d.id)?.situacao) && <span className="fin-tag a-vencer">a pagar</span>}
                          {d.vale_no_mes && d.conta_no_resultado && pagamentoPorDespesa.get(d.id)?.situacao === "sem_data" && <span className="fin-tag">sem vencimento</span>}
                        </small>
                      </span>
                      <Dinheiro valor={d.valor} tamanho="xs" />
                    </LinhaDespesa>
                    {aberto === d.id && (
                      <EditorDespesa
                        escopo={escopo} competencia={competencia} despesa={d} grupos={grupos}
                        aoCancelar={() => setAberto(null)}
                        aoSalvar={(dados) => salvar(d.id, dados)}
                        aoExcluir={async () => { await api.excluirDespesa(d.id); setAberto(null); await recarregar(); }}
                      />
                    )}
                  </li>
                ))}
                {itensTarifa.map((tarifa) => (
                  <li key={`tarifa-${tarifa.id}`}>
                    <div className="fin-despesa-linha fin-despesa-caixa">
                      <span className="fin-despesa-dia">dia<b>{Number(tarifa.data.slice(8))}</b></span>
                      <span className="fin-despesa-texto"><strong>{tarifa.descricao}</strong><small><span className="fin-tag">lançada no Caixa</span></small></span>
                      <Dinheiro valor={tarifa.valor} tamanho="xs" />
                    </div>
                  </li>
                ))}
                {itensDivida.map((divida) => (
                  <li key={`divida-${divida.id}`}>
                    <div className="fin-despesa-linha fin-despesa-caixa">
                      <span className="fin-despesa-dia">{divida.proximo_pagamento ? <>dia<b>{Number(divida.proximo_pagamento.slice(8))}</b></> : <b>—</b>}</span>
                      <span className="fin-despesa-texto">
                        <strong>{divida.credor}</strong>
                        <small>{divida.parcelas_total ? `${divida.parcelas_pagas} de ${divida.parcelas_total} parcelas pagas` : "Dívida ativa"}<Link className="fin-link" to="/financeiro/dividas">ver dívida</Link></small>
                      </span>
                      <Dinheiro valor={divida.valor_parcela} tamanho="xs" />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function EditorDivida({ divida, aoSalvar, aoExcluir, aoCancelar }) {
  const [form, setForm] = useState(() => ({
    credor: divida?.credor || "", valor_total: valorParaCampo(divida?.valor_total), valor_parcela: valorParaCampo(divida?.valor_parcela),
    parcelas_total: divida?.parcelas_total ?? "", parcelas_pagas: divida?.parcelas_pagas ?? 0, observacao: divida?.observacao || "",
    quitada: divida?.quitada || false, congelada: divida?.congelada || false, proximo_pagamento: divida?.proximo_pagamento || "",
  }));
  const [erro, setErro] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const mudar = (campo, valor) => setForm((f) => ({ ...f, [campo]: valor }));
  const total = form.parcelas_total === "" ? null : Number(form.parcelas_total);
  const pagas = Number(form.parcelas_pagas) || 0;

  async function salvar(e) {
    e.preventDefault();
    if (total && pagas > total) return setErro("Parcelas pagas passam do total de parcelas");
    try {
      await aoSalvar({
        credor: form.credor.trim(), valor_total: numeroBr(form.valor_total), valor_parcela: numeroBr(form.valor_parcela),
        parcelas_total: total, parcelas_pagas: pagas, observacao: form.observacao, proximo_pagamento: form.proximo_pagamento || null,
        // Com parcelas, quitada e quando todas foram pagas; sem, vale a marcacao.
        quitada: total ? pagas >= total : form.quitada,
        congelada: form.congelada,
      });
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="fin-form-janela" onSubmit={salvar}>
      <label className="field"><span>Credor</span><input value={form.credor} onChange={(e) => mudar("credor", e.target.value)} required autoFocus /></label>
      <div className="fin-form-dupla">
        <label className="field"><span>Valor total</span><CampoValor valor={form.valor_total} aoMudar={(v) => mudar("valor_total", v)} placeholder="a organizar" /></label>
        <label className="field"><span>Valor da parcela</span><CampoValor valor={form.valor_parcela} aoMudar={(v) => mudar("valor_parcela", v)} /></label>
      </div>
      <div className="fin-form-dupla">
        <label className="field"><span>Parcelas pagas</span><input type="number" min="0" value={form.parcelas_pagas} onChange={(e) => mudar("parcelas_pagas", e.target.value)} /></label>
        <label className="field"><span>Total de parcelas</span><input type="number" min="1" value={form.parcelas_total} onChange={(e) => mudar("parcelas_total", e.target.value)} placeholder="sem parcelas" /></label>
      </div>
      <div className="fin-form-dupla">
        <label className="field"><span>Próximo pagamento</span><input type="date" value={form.proximo_pagamento} onChange={(e) => mudar("proximo_pagamento", e.target.value)} /></label>
        <label className="field"><span>Observação</span><input value={form.observacao} onChange={(e) => mudar("observacao", e.target.value)} placeholder="Ex.: A organizar" /></label>
      </div>
      {total > 0 && <small className="fin-dica">Ao registrar uma parcela paga, o próximo pagamento passa para o mês seguinte.</small>}
      <label className="fin-check"><input type="checkbox" checked={form.congelada} onChange={(e) => mudar("congelada", e.target.checked)} /> Congelar dívida e pausar as parcelas em Gastos</label>
      {!total && <label className="fin-check"><input type="checkbox" checked={form.quitada} onChange={(e) => mudar("quitada", e.target.checked)} /> Quitada</label>}
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <footer className="fin-modal-rodape">
        {divida && (confirmar ? (
          <span className="fin-confirmar">Apagar esta dívida?
            <button type="button" className="btn-ghost perigo" onClick={async () => {
              try { await aoExcluir(); } catch (err) { setErro(err.message); setConfirmar(false); }
            }}>Apagar</button>
            <button type="button" className="btn-ghost" onClick={() => setConfirmar(false)}>Não</button>
          </span>
        ) : <button type="button" className="btn-ghost perigo" onClick={() => setConfirmar(true)}><Icon name="trash" size={14} /> Excluir</button>)}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary">Salvar</button>
      </footer>
    </form>
  );
}

function FormPagamentoDivida({ divida, contas, aoSalvar }) {
  // Sugere a parcela (ou o que falta): quase sempre e o valor que saiu.
  const [valor, setValor] = useState(valorParaCampo(divida.valor_parcela ?? divida.restante));
  const [data, setData] = useState(hojeIso());
  const [contaId, setContaId] = useState("");
  const [observacao, setObservacao] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function salvar(e) {
    e.preventDefault();
    const numero = numeroBr(valor);
    if (!numero || numero <= 0) return setErro("Informe o valor pago");
    setSalvando(true);
    setErro("");
    try {
      await aoSalvar({ valor: numero, pago_em: data, observacao, conta_id: contaId ? Number(contaId) : null });
      setValor(valorParaCampo(divida.valor_parcela));
      setObservacao("");
    } catch (err) {
      setErro(err.message);
    }
    setSalvando(false);
  }

  return (
    <form className="fin-divida-pagar" onSubmit={salvar}>
      <label className="field"><span>Valor pago</span><CampoValor valor={valor} aoMudar={setValor} autoFocus /></label>
      <label className="field"><span>Data do pagamento</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} required /></label>
      {/* Dívida acertada em dinheiro não passou por banco: a conta é opcional, e
          só com ela escolhida a saída aparece no Caixa. */}
      <label className="field"><span>Saiu de</span>
        <select value={contaId} onChange={(e) => setContaId(e.target.value)}>
          <option value="">Não lançar no Caixa</option>
          {contas.map((conta) => <option key={conta.id} value={conta.id}>{conta.nome}</option>)}
        </select>
      </label>
      <label className="field fin-divida-largo"><span>Observação</span>
        <input value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="Opcional. Ex.: adiantamento, acerto no dinheiro" />
      </label>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-modal-rodape">
        <span className="fin-espaco" />
        <button type="submit" className="btn-primary" disabled={salvando}><Icon name="check" size={14} /> {salvando ? "Lançando..." : "Lançar pagamento"}</button>
      </div>
    </form>
  );
}

// O que foi pago da divida: quanto, em que dia e com qual observacao.
function PainelDivida({ divida, contas, aoLancar, aoDesfazer, aoEditar }) {
  const pagamentos = divida.pagamentos || [];
  const [desfazendo, setDesfazendo] = useState(null);
  // Quem so visualiza continua vendo quanto ja pagou, quanto falta e o
  // historico - o que sai e lancar, desfazer e editar a divida.
  const podeGravar = usePodeGravar();
  return (
    <div className="fin-divida-painel">
      <div className="fin-divida-painel-topo">
        <div><span className="eyebrow">JÁ PAGUEI</span><Dinheiro valor={divida.pago} tamanho="m" /></div>
        <div><span className="eyebrow">AINDA FALTA</span><Dinheiro valor={divida.restante} tamanho="m" /></div>
        {podeGravar && <button type="button" className="btn-secondary" onClick={aoEditar}><Icon name="edit" size={14} /> Editar dívida</button>}
      </div>
      {divida.quitada ? <Aviso>Dívida quitada.{podeGravar ? " Desfaça um pagamento pra reabrir." : ""}</Aviso>
        : divida.congelada ? <Aviso tipo="warning">Dívida congelada.{podeGravar ? " Reative no editor pra lançar pagamento." : " As parcelas estão pausadas."}</Aviso>
          : podeGravar && <FormPagamentoDivida divida={divida} contas={contas} aoSalvar={aoLancar} />}
      <section className="fin-divida-historico">
        <h3>Pagamentos lançados</h3>
        {pagamentos.length === 0 ? (
          <small>Nada lançado ainda. {divida.parcelas_pagas > 0 ? `As ${divida.parcelas_pagas} parcelas marcadas antes não guardaram valor nem data.` : ""}</small>
        ) : (
          <ul>
            {pagamentos.map((pagamento) => (
              <li key={pagamento.id}>
                <div>
                  <strong>{diaBr(pagamento.pago_em)}</strong>
                  <small>{[pagamento.no_caixa ? `saiu de ${pagamento.conta}` : "fora do Caixa", pagamento.observacao].filter(Boolean).join(" · ")}</small>
                </div>
                <Dinheiro valor={pagamento.valor} tamanho="xs" />
                {podeGravar && <button type="button" className="btn-ghost perigo" disabled={desfazendo === pagamento.id}
                  onClick={async () => {
                    setDesfazendo(pagamento.id);
                    try { await aoDesfazer(pagamento.id); } catch { /* o erro aparece no aviso da tela */ }
                    setDesfazendo(null);
                  }}>
                  {desfazendo === pagamento.id ? "..." : "Desfazer"}
                </button>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function DataPagamento({ dia }) {
  if (!dia) return <span className="fin-pagamento sem-data">Sem data de pagamento</span>;
  const dias = diasAte(dia);
  const quando = dias === 0 ? "hoje" : dias === 1 ? "amanhã" : dias > 0 ? `em ${dias} dias` : `atrasado há ${-dias} ${dias === -1 ? "dia" : "dias"}`;
  const estado = dias < 0 ? "atrasado" : dias <= 7 ? "perto" : "";
  return (
    <span className={`fin-pagamento ${estado}`}>
      <Icon name="calendar" size={13} />
      <span>Paga em <b>{diaBr(dia)}</b> · {quando}</span>
    </span>
  );
}

export function Dividas({ dividas, recarregar }) {
  const podeGravar = usePodeGravar();
  const [aberto, setAberto] = useState(null);
  const [modo, setModo] = useState("pagamentos");
  const [contas, setContas] = useState([]);
  const [erro, setErro] = useState("");
  // A tela de dividas carrega so as dividas; as contas vem pra ca porque o
  // pagamento pode (se o dono quiser) sair de uma conta e virar saida no Caixa.
  useEffect(() => {
    let vivo = true;
    api.contas().then((lista) => vivo && setContas(lista.filter((c) => c.ativa))).catch(() => {});
    return () => { vivo = false; };
  }, []);
  const emAberto = dividas.filter((d) => !d.quitada);
  const restante = emAberto.reduce((s, d) => s + (d.restante ?? d.valor_total ?? 0), 0);
  const parcelas = emAberto.filter((d) => !d.congelada).reduce((s, d) => s + (d.valor_parcela || 0), 0);
  const editando = aberto && aberto !== "nova" ? dividas.find((d) => d.id === aberto) : null;
  const proxima = emAberto.find((d) => !d.congelada && d.proximo_pagamento);

  async function agir(acao, fechar = true) {
    setErro("");
    try {
      await acao();
      if (fechar) setAberto(null);
      await recarregar();
    } catch (err) {
      setErro(err.message);
      throw err;
    }
  }

  function abrir(id, qual) {
    setModo(qual);
    setAberto(id);
    setErro("");
  }

  return (
    <div className="fin-despesas">
      <div className="fin-despesas-topo">
        <div>
          <span className="eyebrow">AINDA A PAGAR</span>
          <Dinheiro valor={restante} tamanho="l" />
          <small>
            {emAberto.length} dívidas em aberto · {brl(parcelas)} em parcelas por mês
            {proxima && ` · próximo pagamento: ${proxima.credor}, ${diaBr(proxima.proximo_pagamento)}`}
          </small>
        </div>
        {podeGravar && <button type="button" className="btn-primary" onClick={() => abrir("nova", "editar")}><Icon name="plus" size={14} /> Dívida</button>}
      </div>
      {erro && !aberto && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-dividas">
        {dividas.map((d) => {
          const pct = d.parcelas_total ? Math.round((d.parcelas_pagas / d.parcelas_total) * 100) : null;
          const organizar = d.valor_total === null || /organizar/i.test(d.observacao);
          const pagamentos = d.pagamentos || [];
          const ultimo = pagamentos[0];
          return (
            // O card inteiro abre o historico: clicar na divida e ver o que ja
            // foi pago e quando. Os botoes de dentro seguram o clique.
            <section key={d.id} className={`card fin-divida ${d.quitada ? "quitada" : ""} ${d.congelada ? "congelada" : ""}`}
              onClick={() => abrir(d.id, "pagamentos")}>
              <header>
                <h3>{d.credor}</h3>
                {d.quitada ? <b className="fin-situacao pago">Quitada</b> : d.congelada ? <b className="fin-situacao congelada">Congelada</b> : organizar && <b className="fin-situacao hoje">A organizar</b>}
                <button type="button" className="icon-btn" aria-label={`Pagamentos de ${d.credor}`} title="Pagamentos"
                  onClick={(e) => { e.stopPropagation(); abrir(d.id, "pagamentos"); }}><Icon name="wallet" size={14} /></button>
                {podeGravar && <button type="button" className="icon-btn" aria-label={`Editar ${d.credor}`} title="Editar"
                  onClick={(e) => { e.stopPropagation(); abrir(d.id, "editar"); }}><Icon name="edit" size={14} /></button>}
              </header>
              {!d.quitada && !d.congelada && <DataPagamento dia={d.proximo_pagamento} />}
              {d.congelada && <span className="fin-pagamento congelada">Parcelas pausadas · não entra em Gastos</span>}
              <Dinheiro valor={d.restante ?? d.valor_total} tamanho="m" />
              <small className="fin-divida-sub">
                {d.restante !== null ? `falta, de ${brl(d.valor_total ?? d.restante)}` : d.valor_total !== null ? "valor total" : "valor total a definir"}
              </small>
              {pct !== null && (
                <>
                  <span className="fin-progresso"><i style={{ width: `${pct}%` }} /></span>
                  <small>{d.parcelas_pagas} de {d.parcelas_total} parcelas pagas{d.valor_parcela ? ` · ${brl(d.valor_parcela)} cada` : ""}</small>
                </>
              )}
              {pct === null && Boolean(d.valor_parcela) && <small>Parcela de {brl(d.valor_parcela)}</small>}
              <small className="fin-divida-ultimo">
                {ultimo
                  ? <>Último pagamento: <b>{diaBr(ultimo.pago_em)}</b> · {brl(ultimo.valor)}{pagamentos.length > 1 ? ` · ${pagamentos.length} lançados` : ""}</>
                  : d.quitada || d.congelada || !podeGravar ? "Sem pagamento lançado" : "Sem pagamento lançado · clique pra lançar"}
              </small>
              {podeGravar && !d.quitada && !d.congelada && Boolean(d.parcelas_total) && (
                <button type="button" className="btn-secondary fin-divida-acao"
                  title="Marca uma parcela sem guardar valor nem data"
                  onClick={(e) => { e.stopPropagation(); agir(() => api.parcelaPaga(d.id)).catch(() => {}); }}>
                  <Icon name="check" size={14} /> Registrar parcela paga
                </button>
              )}
            </section>
          );
        })}
      </div>
      {aberto && (
        <Modal
          titulo={editando ? `${modo === "editar" ? "Editar dívida" : "Dívida"} · ${editando.credor}` : "Nova dívida"}
          subtitulo={editando && modo === "pagamentos" ? "O que já foi pago, com valor e data de cada vez" : undefined}
          aoFechar={() => setAberto(null)}
          largura={editando && modo === "pagamentos" ? 560 : 480}
        >
          {erro && modo === "pagamentos" && <Aviso tipo="error">{erro}</Aviso>}
          {editando && modo === "pagamentos" ? (
            // Lancar e desfazer nao fecham a janela: o historico recarregado e a
            // resposta do que acabou de ser feito.
            <PainelDivida
              divida={editando}
              contas={contas}
              aoEditar={() => setModo("editar")}
              aoLancar={(dados) => agir(() => api.pagarDivida(editando.id, dados), false)}
              aoDesfazer={(pagamentoId) => agir(() => api.desfazerPagamentoDivida(pagamentoId), false)}
            />
          ) : (
            // O erro do excluir sobe pro editor: divida com pagamento no Caixa e
            // recusada, e o "Apagar" precisa dizer por que nao fez nada.
            <EditorDivida
              divida={editando}
              aoCancelar={() => setAberto(null)}
              aoSalvar={(dados) => agir(() => (editando ? api.atualizarDivida(editando.id, dados) : api.criarDivida(dados)))}
              aoExcluir={() => agir(() => api.excluirDivida(editando.id))}
            />
          )}
        </Modal>
      )}
    </div>
  );
}

// Aba "Pagamentos": o calendario do mes, montado pelos vencimentos.
export function AbaPagamentos({ competencia, agenda, contas, recarregar }) {
  const podeGravar = usePodeGravar();
  const [marcando, setMarcando] = useState(false);
  const [erro, setErro] = useState("");
  // Primeira vez no mes (nada pago ainda e varias vencidas): oferece marcar
  // o que ja passou como pago, pra agenda nao abrir cheia de "atrasado".
  // Marcar as vencidas como pagas e gravacao: so aparece pra administrador.
  const comecando = podeGravar && agenda.totais.pago === 0 && agenda.totais.atrasados >= 3;

  async function marcarVencidas() {
    setMarcando(true);
    setErro("");
    try {
      await api.pagarVencidas(competencia, agenda.hoje);
      await recarregar();
    } catch (err) {
      setErro(err.message);
    } finally {
      setMarcando(false);
    }
  }

  return (
    <>
      <Resumo totais={agenda.totais} />
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      {comecando && (
        <div className="fin-comecando">
          <Icon name="calendar" size={18} />
          <p><b>{agenda.totais.atrasados} contas aparecem atrasadas.</b> Se você já pagou as que venceram antes de hoje, marque todas de uma vez. Não lança nada no caixa; as de hoje continuam em aberto.</p>
          <button type="button" className="btn-secondary" disabled={marcando} onClick={marcarVencidas}>{marcando ? "Marcando..." : `Marcar as ${agenda.totais.atrasados} atrasadas como pagas`}</button>
        </div>
      )}
      <Agenda competencia={competencia} dados={agenda} contas={contas} recarregar={recarregar} />
    </>
  );
}
