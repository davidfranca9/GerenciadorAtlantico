import { useCallback, useEffect, useMemo, useState } from "react";
import { financeiro as api } from "../../api/client";
import Icon from "../../components/Icon";
import { Aviso, CampoValor, Dinheiro, ImportarPlanilha, NavegadorMes } from "./comum";
import { brl, brlCurto, competenciaDe, diaBr, diaPorExtenso, hojeIso, isoDe, numeroBr, valorParaCampo } from "./formato";
import "./financeiro.css";

const ABAS = [
  { valor: "agenda", rotulo: "Agenda" },
  { valor: "empresa", rotulo: "Empresa" },
  { valor: "pessoal", rotulo: "Pessoal" },
  { valor: "dividas", rotulo: "Dívidas" },
];

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
  const vazios = (primeiro.getDay() + 6) % 7;
  const porDia = useMemo(() => {
    const mapa = {};
    for (const item of itens) {
      if (!item.vencimento) continue;
      (mapa[item.vencimento] ||= []).push(item);
    }
    return mapa;
  }, [itens]);

  const celulas = [];
  for (let i = 0; i < vazios; i += 1) celulas.push(<span key={`v${i}`} className="fin-cal-vazio" />);
  for (let d = 1; d <= ultimoDia; d += 1) {
    const iso = isoDe(new Date(ano, mes - 1, d));
    const doDia = porDia[iso] || [];
    const aberto = doDia.filter((i) => i.situacao !== "pago");
    const total = aberto.reduce((soma, i) => soma + (i.valor || 0), 0);
    const estado = doDia.length === 0 ? "" : aberto.length === 0 ? "quitado" : aberto.some((i) => i.situacao === "atrasado") ? "atrasado" : "aberto";
    celulas.push(
      <button
        key={iso}
        type="button"
        className={`fin-cal-dia ${estado} ${iso === hoje ? "hoje" : ""} ${iso === selecionado ? "selecionado" : ""}`}
        onClick={() => aoSelecionar(iso)}
        aria-label={`${diaPorExtenso(iso)}: ${doDia.length} contas`}
      >
        <span className="fin-cal-numero">{d}</span>
        {doDia.length > 0 && (
          <>
            <span className="fin-cal-total">{aberto.length ? (total ? brlCurto(total) : "a definir") : <Icon name="check" size={13} />}</span>
            <span className="fin-cal-pontos">{doDia.slice(0, 5).map((i) => <i key={`${i.origem}${i.id}`} className={SITUACAO[i.situacao].classe} />)}</span>
          </>
        )}
      </button>,
    );
  }
  return (
    <div className="fin-calendario">
      {["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map((d) => <span key={d} className="fin-cal-semana">{d}</span>)}
      {celulas}
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

function ItemAgenda({ item, contas, competencia, aoPagar, aoDesfazer, aoExcluirAvulsa }) {
  const [pagando, setPagando] = useState(false);
  const situacao = SITUACAO[item.situacao];
  return (
    <li className={`fin-conta ${situacao.classe}`}>
      <div className="fin-conta-linha">
        <span className="fin-conta-texto">
          <strong>{item.descricao}{item.parcela && <em>{item.parcela}</em>}</strong>
          <small>
            <span className={`fin-escopo ${item.escopo}`}>{item.escopo === "empresa" ? "Empresa" : "Pessoal"}</span>
            {item.grupo}
            {item.pagamento && ` · pago em ${diaBr(item.pagamento.pago_em)}${item.pagamento.conta ? ` pelo ${item.pagamento.conta}` : ""}`}
          </small>
        </span>
        <span className="fin-conta-valor">
          {item.valor === null && !item.pagamento ? <em>valor a definir</em> : <Dinheiro valor={item.pagamento ? item.pagamento.valor : item.valor} tamanho="s" />}
          <b className={`fin-situacao ${situacao.classe}`}>{situacao.rotulo}</b>
        </span>
        <span className="fin-conta-acoes">
          {item.pagamento ? (
            <button type="button" className="btn-ghost" onClick={() => aoDesfazer(item)} title="Desfazer pagamento">Desfazer</button>
          ) : (
            <button type="button" className="btn-secondary" onClick={() => setPagando(!pagando)}>{pagando ? "Fechar" : "Pagar"}</button>
          )}
          {item.origem === "avulsa" && !item.pagamento && (
            <button type="button" className="icon-btn" aria-label="Excluir conta avulsa" title="Excluir conta avulsa" onClick={() => aoExcluirAvulsa(item)}><Icon name="trash" size={14} /></button>
          )}
        </span>
      </div>
      {pagando && (
        <FormPagar item={item} contas={contas} competencia={competencia} aoCancelar={() => setPagando(false)} aoPagar={async (p) => { await aoPagar(p); setPagando(false); }} />
      )}
    </li>
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

function Agenda({ competencia, dados, contas, recarregar }) {
  const hoje = dados.hoje;
  const [dia, setDia] = useState(null);
  const [novaAvulsa, setNovaAvulsa] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    // Abre no dia de hoje se ele e do mes; senao, no primeiro dia com conta.
    if (competenciaDe(hoje) === competencia) setDia(hoje);
    else setDia(dados.itens.find((i) => i.vencimento)?.vencimento || `${competencia}-01`);
  }, [competencia]); // eslint-disable-line react-hooks/exhaustive-deps

  const doDia = dados.itens.filter((i) => i.vencimento === dia);
  const semData = dados.itens.filter((i) => !i.vencimento);
  const atrasadas = dados.itens.filter((i) => i.situacao === "atrasado" && i.vencimento !== dia);

  async function agir(acao) {
    setErro("");
    try {
      await acao();
      await recarregar();
    } catch (err) {
      setErro(err.message);
    }
  }

  const lista = (itens) => (
    <ul className="fin-contas">
      {itens.map((item) => (
        <ItemAgenda
          key={`${item.origem}-${item.id}`}
          item={item}
          contas={contas}
          competencia={competencia}
          aoPagar={(p) => agir(() => api.pagar(p))}
          aoDesfazer={(i) => agir(() => api.desfazerPagamento({ origem: i.origem, origem_id: i.id, competencia }))}
          aoExcluirAvulsa={(i) => agir(() => api.excluirAvulsa(i.id))}
        />
      ))}
    </ul>
  );

  return (
    <div className="fin-agenda">
      <section className="card">
        <Calendario competencia={competencia} itens={dados.itens} hoje={hoje} selecionado={dia} aoSelecionar={setDia} />
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
          <button type="button" className="btn-secondary" onClick={() => setNovaAvulsa(!novaAvulsa)}><Icon name="plus" size={14} /> Conta avulsa</button>
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
        {semData.length > 0 && (
          <details className="fin-secao">
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
            <button type="button" className="btn-ghost perigo" onClick={aoExcluir}>Apagar</button>
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

function Despesas({ escopo, competencia, despesas, recarregar }) {
  const [aberto, setAberto] = useState(null);
  const minhas = despesas.filter((d) => d.escopo === escopo);
  const grupos = [...new Set(minhas.map((d) => d.grupo))];
  const doMes = minhas.filter((d) => d.vale_no_mes && d.conta_no_resultado);
  const total = doMes.reduce((s, d) => s + d.valor, 0);

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
          <small>{doMes.length} contas fixas em {grupos.length} grupos</small>
        </div>
        <button type="button" className="btn-primary" onClick={() => setAberto(aberto === "nova" ? null : "nova")}><Icon name="plus" size={14} /> Despesa</button>
      </div>
      {aberto === "nova" && (
        <div className="card"><EditorDespesa escopo={escopo} competencia={competencia} grupos={grupos} aoCancelar={() => setAberto(null)} aoSalvar={(d) => salvar(null, d)} /></div>
      )}
      {minhas.length === 0 && aberto !== "nova" && (
        <div className="card fin-sem-itens"><Icon name="calendar" size={22} /><p>Nenhuma despesa {escopo === "empresa" ? "da empresa" : "pessoal"} cadastrada. Importe a planilha do Controle de Carregamentos ou adicione a primeira.</p></div>
      )}
      <div className="fin-grupos">
        {grupos.map((grupo) => {
          const itens = minhas.filter((d) => d.grupo === grupo);
          const subtotal = itens.filter((d) => d.vale_no_mes && d.conta_no_resultado).reduce((s, d) => s + d.valor, 0);
          return (
            <section key={grupo} className="card fin-grupo">
              <header><h3>{grupo}</h3><Dinheiro valor={subtotal} tamanho="xs" /></header>
              <ul>
                {itens.map((d) => (
                  <li key={d.id} className={`${!d.vale_no_mes || !d.ativa ? "fora" : ""} ${aberto === d.id ? "aberto" : ""}`}>
                    <button type="button" className="fin-despesa-linha" onClick={() => setAberto(aberto === d.id ? null : d.id)} aria-expanded={aberto === d.id}>
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
                        </small>
                      </span>
                      <Dinheiro valor={d.valor} tamanho="xs" />
                    </button>
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
  }));
  const [erro, setErro] = useState("");
  const mudar = (campo, valor) => setForm((f) => ({ ...f, [campo]: valor }));

  async function salvar(e) {
    e.preventDefault();
    try {
      await aoSalvar({
        credor: form.credor.trim(), valor_total: numeroBr(form.valor_total), valor_parcela: numeroBr(form.valor_parcela),
        parcelas_total: form.parcelas_total === "" ? null : Number(form.parcelas_total), parcelas_pagas: Number(form.parcelas_pagas) || 0,
        observacao: form.observacao, quitada: divida?.quitada || false,
      });
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <form className="fin-editor-divida" onSubmit={salvar}>
      <div className="fin-editor-grade">
        <label className="field fin-editor-largo"><span>Credor</span><input value={form.credor} onChange={(e) => mudar("credor", e.target.value)} required autoFocus /></label>
        <label className="field"><span>Valor total</span><CampoValor valor={form.valor_total} aoMudar={(v) => mudar("valor_total", v)} placeholder="a organizar" /></label>
        <label className="field"><span>Parcela</span><CampoValor valor={form.valor_parcela} aoMudar={(v) => mudar("valor_parcela", v)} /></label>
        <label className="field"><span>Parcelas pagas</span><input type="number" min="0" value={form.parcelas_pagas} onChange={(e) => mudar("parcelas_pagas", e.target.value)} /></label>
        <label className="field"><span>De quantas</span><input type="number" min="1" value={form.parcelas_total} onChange={(e) => mudar("parcelas_total", e.target.value)} placeholder="—" /></label>
        <label className="field fin-editor-largo"><span>Observação</span><input value={form.observacao} onChange={(e) => mudar("observacao", e.target.value)} placeholder="Ex.: A organizar" /></label>
      </div>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-editor-acoes">
        {divida && <button type="button" className="btn-ghost perigo" onClick={aoExcluir}><Icon name="trash" size={14} /> Excluir</button>}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" className="btn-primary">Salvar</button>
      </div>
    </form>
  );
}

function Dividas({ dividas, recarregar }) {
  const [aberto, setAberto] = useState(null);
  const [erro, setErro] = useState("");
  const emAberto = dividas.filter((d) => !d.quitada);
  const restante = emAberto.reduce((s, d) => s + (d.restante ?? d.valor_total ?? 0), 0);
  const parcelas = emAberto.reduce((s, d) => s + (d.valor_parcela || 0), 0);

  async function agir(acao) {
    setErro("");
    try {
      await acao();
      setAberto(null);
      await recarregar();
    } catch (err) {
      setErro(err.message);
    }
  }

  return (
    <div className="fin-despesas">
      <div className="fin-despesas-topo">
        <div>
          <span className="eyebrow">AINDA A PAGAR</span>
          <Dinheiro valor={restante} tamanho="l" />
          <small>{emAberto.length} dívidas em aberto · {brl(parcelas)} em parcelas por mês</small>
        </div>
        <button type="button" className="btn-primary" onClick={() => setAberto(aberto === "nova" ? null : "nova")}><Icon name="plus" size={14} /> Dívida</button>
      </div>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      {aberto === "nova" && <div className="card"><EditorDivida aoCancelar={() => setAberto(null)} aoSalvar={(d) => agir(() => api.criarDivida(d))} /></div>}
      <div className="fin-dividas">
        {dividas.map((d) => {
          const pct = d.parcelas_total ? Math.round((d.parcelas_pagas / d.parcelas_total) * 100) : null;
          const organizar = d.valor_total === null || /organizar/i.test(d.observacao);
          return (
            <section key={d.id} className={`card fin-divida ${d.quitada ? "quitada" : ""}`}>
              {aberto === d.id ? (
                <EditorDivida divida={d} aoCancelar={() => setAberto(null)} aoSalvar={(dados) => agir(() => api.atualizarDivida(d.id, dados))} aoExcluir={() => agir(() => api.excluirDivida(d.id))} />
              ) : (
                <>
                  <header>
                    <h3>{d.credor}</h3>
                    {d.quitada ? <b className="fin-situacao pago">Quitada</b> : organizar && <b className="fin-situacao hoje">A organizar</b>}
                    <button type="button" className="icon-btn" aria-label={`Editar ${d.credor}`} onClick={() => setAberto(d.id)}><Icon name="edit" size={14} /></button>
                  </header>
                  <Dinheiro valor={d.restante ?? d.valor_total} tamanho="m" />
                  <small className="fin-divida-sub">{d.restante !== null ? `falta de ${brl(d.valor_total ?? d.restante)}` : d.valor_total !== null ? "valor total" : "valor total a definir"}</small>
                  {pct !== null && (
                    <>
                      <span className="fin-progresso"><i style={{ width: `${pct}%` }} /></span>
                      <small>{d.parcelas_pagas} de {d.parcelas_total} parcelas pagas{d.valor_parcela ? ` · ${brl(d.valor_parcela)} cada` : ""}</small>
                    </>
                  )}
                  {pct === null && d.valor_parcela && <small>Parcela de {brl(d.valor_parcela)}</small>}
                  {!d.quitada && d.parcelas_total && (
                    <button type="button" className="btn-secondary fin-divida-acao" onClick={() => agir(() => api.parcelaPaga(d.id))}><Icon name="check" size={14} /> Registrar parcela paga</button>
                  )}
                </>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

export default function ContasPagarPage() {
  const [competencia, setCompetencia] = useState(competenciaDe(hojeIso()));
  const [aba, setAba] = useState("agenda");
  const [agenda, setAgenda] = useState(null);
  const [despesas, setDespesas] = useState([]);
  const [dividas, setDividas] = useState([]);
  const [contas, setContas] = useState([]);
  const [erro, setErro] = useState("");
  const [modal, setModal] = useState(false);
  const [marcando, setMarcando] = useState(false);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      const [a, d, dv, c] = await Promise.all([api.agenda(competencia), api.despesas(competencia), api.dividas(), api.contas()]);
      setAgenda(a);
      setDespesas(d);
      setDividas(dv);
      setContas(c.filter((conta) => conta.ativa));
    } catch (err) {
      setErro(err.message);
    }
  }, [competencia]);

  useEffect(() => { carregar(); }, [carregar]);

  // Primeira vez no mes (nada pago ainda e varias vencidas): oferece marcar
  // o que ja passou como pago, pra agenda nao abrir cheia de "atrasado".
  const comecando = agenda && agenda.totais.pago === 0 && agenda.totais.atrasados >= 3;

  async function marcarVencidas() {
    setMarcando(true);
    try {
      await api.pagarVencidas(competencia, agenda.hoje);
      await carregar();
    } catch (err) {
      setErro(err.message);
    } finally {
      setMarcando(false);
    }
  }

  return (
    <div className="ops-page fin-pagina">
      <div className="fin-barra">
        <NavegadorMes competencia={competencia} aoMudar={setCompetencia} />
        <div className="fin-segmentado" role="tablist">
          {ABAS.map((a) => (
            <button key={a.valor} type="button" role="tab" aria-selected={aba === a.valor} className={aba === a.valor ? "ativo" : ""} onClick={() => setAba(a.valor)}>{a.rotulo}</button>
          ))}
        </div>
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={() => setModal(true)}><Icon name="upload" size={15} /> Importar planilha</button>
      </div>

      {erro && <Aviso tipo="error">{erro}</Aviso>}
      {!agenda && !erro && <Aviso>Carregando as contas...</Aviso>}

      {agenda && (
        <>
          <Resumo totais={agenda.totais} />
          {comecando && aba === "agenda" && (
            <div className="fin-comecando">
              <Icon name="calendar" size={18} />
              <p><b>{agenda.totais.atrasados} contas aparecem atrasadas.</b> Se você já pagou as que venceram antes de hoje, marque todas de uma vez. Não lança nada no caixa; as de hoje continuam em aberto.</p>
              <button type="button" className="btn-secondary" disabled={marcando} onClick={marcarVencidas}>{marcando ? "Marcando..." : `Marcar as ${agenda.totais.atrasados} atrasadas como pagas`}</button>
            </div>
          )}
          {aba === "agenda" && <Agenda competencia={competencia} dados={agenda} contas={contas} recarregar={carregar} />}
          {aba === "empresa" && <Despesas escopo="empresa" competencia={competencia} despesas={despesas} recarregar={carregar} />}
          {aba === "pessoal" && <Despesas escopo="pessoal" competencia={competencia} despesas={despesas} recarregar={carregar} />}
          {aba === "dividas" && <Dividas dividas={dividas} recarregar={carregar} />}
        </>
      )}

      {modal && <ImportarPlanilha aoFechar={() => setModal(false)} aoImportar={(r) => { if (r.competencia) setCompetencia(r.competencia); carregar(); }} />}
    </div>
  );
}
