import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { financeiro as api } from "../../api/client";
import Icon from "../../components/Icon";
import { Aviso, CampoValor, Dinheiro, ImportarPlanilha, NavegadorMes } from "./comum";
import { AbaPagamentos, Despesas, Dividas } from "./ContasPagarPage";
import { brl, competenciaDe, hojeIso, nomeCompetencia, numeroBr, toneladas, valorParaCampo } from "./formato";
import { AbaLucroBruto } from "./ResultadoPage";
import "./financeiro.css";

function payloadDespesa(d, mudanca) {
  return {
    escopo: d.escopo, grupo: d.grupo, descricao: d.descricao, dia_vencimento: d.dia_vencimento, valor: d.valor,
    parcela_inicial: d.parcela_inicial, parcelas_total: d.parcelas_total, competencia_inicio: d.competencia_inicio,
    conta_no_resultado: d.conta_no_resultado, entra_precificacao: d.entra_precificacao, ativa: d.ativa, ordem: d.ordem,
    ...mudanca,
  };
}

function arredondar(valor, casas = 2) {
  const fator = 10 ** casas;
  return Math.round((valor || 0) * fator) / fator;
}

// Aba "Precificação CT-e": o que entra no custo fixo, quanto cada tonelada
// precisa pagar e o frete minimo pra nao dar prejuizo.
function AbaPrecificacao({ competencia, resultado, despesas, recarregar }) {
  const empresa = despesas.filter((d) => d.escopo === "empresa" && d.vale_no_mes && d.ativa);
  const entram = empresa.filter((d) => d.entra_precificacao);
  const fora = empresa.filter((d) => !d.entra_precificacao);
  const custoFixo = arredondar(entram.reduce((s, d) => s + d.valor, 0));
  const r = resultado.resumo;
  const [verFora, setVerFora] = useState(false);
  const [salvando, setSalvando] = useState(null);
  const [erro, setErro] = useState("");

  const padrao = () => ({
    toneladas: valorParaCampo(arredondar(resultado.meta.toneladas || r.toneladas || 0, 1)),
    frete: valorParaCampo(arredondar(r.toneladas ? r.frete_empresa / r.toneladas : 0)),
    variavel: valorParaCampo(arredondar(r.toneladas ? (r.frete_motorista + r.agenciamento + r.comissao) / r.toneladas : 0)),
  });
  const [sim, setSim] = useState(padrao);
  useEffect(() => setSim(padrao()), [competencia]); // eslint-disable-line react-hooks/exhaustive-deps

  const t = numeroBr(sim.toneladas) || 0;
  const frete = numeroBr(sim.frete) || 0;
  const variavel = numeroBr(sim.variavel) || 0;
  const fixoPorT = t ? custoFixo / t : null;
  const margemPorT = frete - variavel;
  const lucroPorT = fixoPorT === null ? null : margemPorT - fixoPorT;
  const freteMinimo = fixoPorT === null ? null : variavel + fixoPorT;

  async function alternar(d) {
    setSalvando(d.id);
    setErro("");
    try {
      await api.atualizarDespesa(d.id, payloadDespesa(d, { entra_precificacao: !d.entra_precificacao }));
      await recarregar();
    } catch (err) {
      setErro(err.message);
    } finally {
      setSalvando(null);
    }
  }

  const linha = (d, incluida) => (
    <li key={d.id} className={incluida ? "" : "fora"}>
      <span className="fin-preco-texto">
        <strong>{d.descricao}</strong>
        <small>{d.grupo}{!d.conta_no_resultado && " · só na precificação"}</small>
      </span>
      <Dinheiro valor={d.valor} tamanho="xs" />
      <button type="button" className={incluida ? "btn-ghost" : "btn-secondary"} disabled={salvando === d.id} onClick={() => alternar(d)}>
        {salvando === d.id ? "..." : incluida ? "Tirar" : "Incluir"}
      </button>
    </li>
  );

  return (
    <>
      <section className="fin-resumo-contas">
        <div className="card">
          <span className="eyebrow">CUSTO FIXO DO MÊS</span>
          <Dinheiro valor={custoFixo} tamanho="l" />
          <small>{entram.length} despesas entram no preço do CT-e</small>
        </div>
        <div className="card">
          <span className="eyebrow">POR TONELADA CARREGADA</span>
          <Dinheiro valor={r.toneladas ? custoFixo / r.toneladas : null} tamanho="l" />
          <small>{r.toneladas ? `dividido pelas ${toneladas(r.toneladas)} de ${nomeCompetencia(competencia).toLowerCase()}` : "sem carregamentos no mês"}</small>
        </div>
        <div className={`card ${r.lucro_por_tonelada !== null && r.toneladas && r.lucro_por_tonelada < custoFixo / r.toneladas ? "alerta" : ""}`}>
          <span className="eyebrow">PONTO DE EQUILÍBRIO</span>
          <strong className="fin-numero-grande">{resultado.precificacao.ponto_de_equilibrio_ton !== null ? toneladas(resultado.precificacao.ponto_de_equilibrio_ton, 0) : "—"}</strong>
          <small>{r.lucro_por_tonelada !== null ? `no mês, com ${brl(r.lucro_por_tonelada)} de lucro por tonelada` : "precisa de carregamentos pra calcular"}</small>
        </div>
      </section>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      <div className="fin-preco-grade">
        <section className="card fin-preco-lista">
          <header className="fin-extrato-topo">
            <div><h3>Custos que entram no preço</h3><p>Soma dividida pelas toneladas do mês</p></div>
            <Dinheiro valor={custoFixo} tamanho="s" />
          </header>
          {entram.length === 0 ? <p className="fin-sem-itens">Nenhuma despesa marcada. Inclua abaixo as que pesam no preço do frete.</p> : <ul>{entram.map((d) => linha(d, true))}</ul>}
          {fora.length > 0 && (
            <details className="fin-secao" open={verFora} onToggle={(e) => setVerFora(e.currentTarget.open)}>
              <summary className="fin-subtitulo">Outras despesas da empresa <b>{fora.length} · {brl(fora.reduce((s, d) => s + d.valor, 0))}</b></summary>
              <ul>{fora.map((d) => linha(d, false))}</ul>
            </details>
          )}
        </section>
        <section className="card fin-simulador">
          <header>
            <h3>Simulador de frete</h3>
            <p>Começa com a meta e as médias de {nomeCompetencia(competencia).toLowerCase()}. Mude os números para testar um preço.</p>
          </header>
          <label className="field"><span>Toneladas no mês</span><input inputMode="decimal" value={sim.toneladas} onChange={(e) => setSim({ ...sim, toneladas: e.target.value })} /></label>
          <label className="field"><span>Frete cobrado por tonelada</span><CampoValor valor={sim.frete} aoMudar={(v) => setSim({ ...sim, frete: v })} /></label>
          <label className="field"><span>Motorista + agenciamento + comissão por tonelada</span><CampoValor valor={sim.variavel} aoMudar={(v) => setSim({ ...sim, variavel: v })} /></label>
          <dl className="fin-simulacao">
            <div><dt>Sobra por tonelada, antes do fixo</dt><dd>{brl(margemPorT)}</dd></div>
            <div><dt>Custo fixo por tonelada</dt><dd>{fixoPorT === null ? "—" : `− ${brl(fixoPorT)}`}</dd></div>
            <div className={lucroPorT !== null && lucroPorT < 0 ? "negativo" : "positivo"}><dt>Lucro por tonelada</dt><dd>{lucroPorT === null ? "—" : brl(lucroPorT)}</dd></div>
            <div className={lucroPorT !== null && lucroPorT < 0 ? "negativo" : "positivo"}><dt>Lucro no mês</dt><dd>{lucroPorT === null ? "—" : brl(lucroPorT * t)}</dd></div>
          </dl>
          <div className="fin-frete-minimo">
            <span>Frete mínimo por tonelada, sem prejuízo</span>
            <strong>{freteMinimo === null ? "—" : brl(freteMinimo)}</strong>
          </div>
          <button type="button" className="btn-ghost" onClick={() => setSim(padrao())}>Voltar para a média do mês</button>
        </section>
      </div>
    </>
  );
}

// ----------------------------------------------------------------------------
// Uma pagina por parte da planilha "Controle de carregamentos", cada uma com
// o seu item no menu. O mes escolhido acompanha de uma pagina pra outra.
// ----------------------------------------------------------------------------

const CHAVE_MES = "financeiro.competencia";

export function useCompetencia() {
  const [competencia, setCompetencia] = useState(() => {
    try {
      const salvo = sessionStorage.getItem(CHAVE_MES);
      if (/^\d{4}-\d{2}$/.test(salvo || "")) return salvo;
    } catch {
      /* sem storage: comeca no mes atual */
    }
    return competenciaDe(hojeIso());
  });
  const mudar = useCallback((nova) => {
    setCompetencia(nova);
    try {
      sessionStorage.setItem(CHAVE_MES, nova);
    } catch {
      /* so nao lembra o mes */
    }
  }, []);
  return [competencia, mudar];
}

export function useDados(buscar, chave) {
  const [estado, setEstado] = useState({ chave: null, dados: null });
  const [erro, setErro] = useState("");
  const carregar = useCallback(async () => {
    setErro("");
    try {
      const dados = await buscar();
      setEstado({ chave, dados });
    } catch (err) {
      setErro(err.message);
    }
  }, [chave]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { carregar(); }, [carregar]);
  return { dados: estado.chave === chave ? estado.dados : null, erro, carregar };
}

export function Moldura({ competencia, aoMudarMes, erro, carregando, aoImportar, extras, children }) {
  const [importando, setImportando] = useState(false);
  return (
    <div className="ops-page fin-pagina">
      <div className="fin-barra">
        {competencia && <NavegadorMes competencia={competencia} aoMudar={aoMudarMes} />}
        {extras}
        <span className="fin-espaco" />
        <button type="button" className="btn-secondary" onClick={() => setImportando(true)}><Icon name="upload" size={15} /> Importar planilha</button>
      </div>
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      {carregando && !erro && <Aviso>Carregando...</Aviso>}
      {children}
      {importando && (
        <ImportarPlanilha
          aoFechar={() => setImportando(false)}
          aoImportar={(r) => { if (r.competencia && aoMudarMes) aoMudarMes(r.competencia); aoImportar(); }}
        />
      )}
    </div>
  );
}

export function LucroBrutoPage() {
  const [competencia, setCompetencia] = useCompetencia();
  const { dados, erro, carregar } = useDados(() => api.resultado(competencia), competencia);
  return (
    <Moldura competencia={competencia} aoMudarMes={setCompetencia} erro={erro} carregando={!dados} aoImportar={carregar}>
      {dados && <AbaLucroBruto competencia={competencia} dados={dados} recarregar={carregar} />}
    </Moldura>
  );
}

const ABAS_GASTOS = [
  { valor: "empresa", rotulo: "Empresa", icone: "clipboard" },
  { valor: "pessoal", rotulo: "Pessoal", icone: "users" },
];

export function GastosPage() {
  const [competencia, setCompetencia] = useCompetencia();
  const [busca, setBusca] = useSearchParams();
  const escopo = busca.get("aba") === "pessoal" ? "pessoal" : "empresa";
  const { dados, erro, carregar } = useDados(
    async () => {
      const [resultado, despesas, dividas, pagamentos] = await Promise.all([
        api.resultado(competencia), api.despesas(competencia), api.dividas(), api.agenda(competencia),
      ]);
      return { resultado, despesas, dividas, pagamentos };
    },
    competencia,
  );
  const r = dados?.resultado;
  return (
    <Moldura competencia={competencia} aoMudarMes={setCompetencia} erro={erro} carregando={!dados} aoImportar={carregar}>
      <nav className="fin-abas" role="tablist" aria-label="Gastos">
        {ABAS_GASTOS.map((a) => (
          <button
            key={a.valor} type="button" role="tab" aria-selected={escopo === a.valor} className={escopo === a.valor ? "ativa" : ""}
            onClick={() => setBusca(a.valor === "empresa" ? {} : { aba: a.valor }, { replace: true })}
          >
            <Icon name={a.icone} size={15} />{a.rotulo}
          </button>
        ))}
      </nav>
      {dados && (
        <Despesas
          key={escopo}
          escopo={escopo} competencia={competencia} despesas={dados.despesas} recarregar={carregar}
          tarifas={escopo === "empresa" ? r.despesas.itens_tarifas || [] : []}
          dividas={escopo === r.despesas.escopo_dividas ? dados.dividas.filter((d) => !d.quitada && !d.congelada) : []}
          pagamentos={dados.pagamentos.itens}
          fechamento={escopo === "empresa"
            ? [{ rotulo: "Lucro bruto", valor: r.resumo.lucro_bruto }, { rotulo: "Lucro real", valor: r.lucro_real, destaque: true }]
            : [{ rotulo: "Lucro real da empresa", valor: r.lucro_real }, { rotulo: "Sobra do mês", valor: r.sobra, destaque: true }]}
        />
      )}
    </Moldura>
  );
}

export function PrecificacaoPage() {
  const [competencia, setCompetencia] = useCompetencia();
  const { dados, erro, carregar } = useDados(
    async () => {
      const [resultado, despesas] = await Promise.all([api.resultado(competencia), api.despesas(competencia)]);
      return { resultado, despesas };
    },
    competencia,
  );
  return (
    <Moldura competencia={competencia} aoMudarMes={setCompetencia} erro={erro} carregando={!dados} aoImportar={carregar}>
      {dados && <AbaPrecificacao competencia={competencia} resultado={dados.resultado} despesas={dados.despesas} recarregar={carregar} />}
    </Moldura>
  );
}

export function PagamentosPage() {
  const [competencia, setCompetencia] = useCompetencia();
  const { dados, erro, carregar } = useDados(
    async () => {
      const [agenda, contas] = await Promise.all([api.agenda(competencia), api.contas()]);
      return { agenda, contas: contas.filter((c) => c.ativa) };
    },
    competencia,
  );
  return (
    <Moldura competencia={competencia} aoMudarMes={setCompetencia} erro={erro} carregando={!dados} aoImportar={carregar}>
      {dados && <AbaPagamentos competencia={competencia} agenda={dados.agenda} contas={dados.contas} recarregar={carregar} />}
    </Moldura>
  );
}

const SITUACAO_FATURA = {
  prevista: "Prevista", hoje: "Vence hoje", vencida: "Vencida", sem_cte: "Aguardando CT-e", removida: "Fora da fatura",
};

export function FaturasPage() {
  const [competencia, setCompetencia] = useCompetencia();
  const { dados, erro, carregar } = useDados(() => api.faturas(competencia), competencia);
  const [alterando, setAlterando] = useState(null);
  const [visualizacao, setVisualizacao] = useState("todos");
  const [inicioSemana, setInicioSemana] = useState(() => inicioDaSemana(hojeIso()));
  useEffect(() => {
    const ancora = hojeIso().startsWith(competencia) ? hojeIso() : `${competencia}-01`;
    setInicioSemana(inicioDaSemana(ancora));
  }, [competencia]);

  function inicioDaSemana(iso) {
    const data = new Date(`${iso}T12:00:00`);
    const recuo = (data.getDay() + 6) % 7;
    data.setDate(data.getDate() - recuo);
    return data.toISOString().slice(0, 10);
  }
  function moverSemana(dias) {
    const data = new Date(`${inicioSemana}T12:00:00`);
    data.setDate(data.getDate() + dias);
    setInicioSemana(data.toISOString().slice(0, 10));
  }
  const fimSemanaData = new Date(`${inicioSemana}T12:00:00`);
  fimSemanaData.setDate(fimSemanaData.getDate() + 6);
  const fimSemana = fimSemanaData.toISOString().slice(0, 10);
  const itensVisiveis = dados ? (visualizacao === "todos" ? dados.itens : dados.itens.filter((item) => item.vencimento && item.vencimento >= inicioSemana && item.vencimento <= fimSemana)) : [];
  const incluidosVisiveis = itensVisiveis.filter((item) => item.incluida);
  const totaisVisiveis = dados && visualizacao === "todos" ? dados.totais : {
    previsto: incluidosVisiveis.reduce((s, item) => s + item.valor, 0),
    vencido: incluidosVisiveis.filter((item) => item.situacao === "vencida").reduce((s, item) => s + item.valor, 0),
    sem_cte: 0,
    quantidade: incluidosVisiveis.length,
    removidas: itensVisiveis.length - incluidosVisiveis.length,
  };
  const periodoSemana = `${new Date(`${inicioSemana}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })} a ${fimSemanaData.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}`;
  async function alterar(item) {
    setAlterando(item.id);
    try {
      await api.alterarFatura(item.id, !item.incluida);
      await carregar();
    } finally {
      setAlterando(null);
    }
  }
  return (
    <Moldura competencia={competencia} aoMudarMes={setCompetencia} erro={erro} carregando={!dados} aoImportar={carregar}>
      {dados && <>
        <section className="fin-resumo-contas">
          <div className="card"><span className="eyebrow">PREVISÃO {visualizacao === "semana" ? "DA SEMANA" : "DO MÊS"}</span><Dinheiro valor={totaisVisiveis.previsto} tamanho="l" /><small>{totaisVisiveis.quantidade} autorizações incluídas · prazo padrão de {dados.prazo_dias} dias após o CT-e{totaisVisiveis.removidas ? ` · ${totaisVisiveis.removidas} fora da fatura` : ""}</small></div>
          <div className={`card ${totaisVisiveis.vencido > 0 ? "alerta" : ""}`}><span className="eyebrow">VENCIDO</span><Dinheiro valor={totaisVisiveis.vencido} tamanho="l" /><small>Valores cuja previsão já passou</small></div>
          <div className="card"><span className="eyebrow">AGUARDANDO CT-e</span><Dinheiro valor={totaisVisiveis.sem_cte} tamanho="l" /><small>{visualizacao === "semana" ? "Disponível na visualização Todos" : "Sem data de vencimento até o CT-e ser liberado"}</small></div>
        </section>
        <section className="card fin-faturas">
          <header className="fin-extrato-topo"><div><h3>Faturas de abastecimento</h3><p>Previsão calculada automaticamente: emissão do CT-e + {dados.prazo_dias} dias</p></div><div className="fin-fatura-controles">
            {visualizacao === "semana" && <div className="fin-nav-periodo"><button type="button" className="icon-btn" onClick={() => moverSemana(-7)} aria-label="Semana anterior"><Icon name="chevron-left" size={15} /></button><strong>{periodoSemana}</strong><button type="button" className="icon-btn" onClick={() => moverSemana(7)} aria-label="Próxima semana"><Icon name="chevron-right" size={15} /></button></div>}
            <div className="fin-segmentado pequeno"><button type="button" className={visualizacao === "semana" ? "ativo" : ""} onClick={() => setVisualizacao("semana")}>Semana</button><button type="button" className={visualizacao === "todos" ? "ativo" : ""} onClick={() => setVisualizacao("todos")}>Todos</button></div>
          </div></header>
          {itensVisiveis.length === 0 ? <div className="fin-sem-itens"><Icon name="file" size={22} /><p>Nenhuma fatura prevista {visualizacao === "semana" ? "nesta semana" : "neste mês"}.</p></div> : <div className="fin-faturas-tabela"><table><thead><tr><th>Previsão</th><th>Autorização</th><th>Motorista</th><th>CT-e</th><th>Emissão</th><th>Situação</th><th>Valor</th><th></th></tr></thead><tbody>
            {itensVisiveis.map((item) => <tr key={item.id} className={!item.incluida ? "removida" : ""}><td>{item.vencimento ? new Date(`${item.vencimento}T12:00:00`).toLocaleDateString("pt-BR") : "—"}</td><td>{item.autorizacao || `#${item.id}`}</td><td><strong>{item.motorista}</strong></td><td>{item.cte || "—"}</td><td>{item.data_cte ? new Date(`${item.data_cte}T12:00:00`).toLocaleDateString("pt-BR") : "—"}</td><td><span className={`fin-situacao ${item.situacao}`}>{SITUACAO_FATURA[item.situacao]}</span></td><td><Dinheiro valor={item.valor} tamanho="xs" /></td><td><button type="button" className={item.incluida ? "btn-ghost" : "btn-secondary"} disabled={alterando === item.id} onClick={() => alterar(item)}>{alterando === item.id ? "..." : item.incluida ? "Remover" : "Incluir"}</button></td></tr>)}
          </tbody></table></div>}
        </section>
      </>}
    </Moldura>
  );
}

function FormPagamentoComissao({ grupo, contas, aoSalvar, aoCancelar }) {
  const [valor, setValor] = useState(valorParaCampo(grupo.pendente));
  const [data, setData] = useState(hojeIso());
  const [contaId, setContaId] = useState(contas[0]?.id ? String(contas[0].id) : "");
  const [observacao, setObservacao] = useState("");
  const [erro, setErro] = useState("");
  async function salvar(e) {
    e.preventDefault();
    const numero = numeroBr(valor);
    if (!numero || numero <= 0) return setErro("Informe o valor pago");
    try {
      await aoSalvar({ beneficiario: grupo.beneficiario, valor: numero, pago_em: data, conta_id: contaId ? Number(contaId) : null, observacao });
    } catch (err) {
      setErro(err.message);
    }
  }
  return <form className="fin-comissao-pagar" onSubmit={salvar}>
    <label className="field"><span>Valor pago</span><CampoValor valor={valor} aoMudar={setValor} /></label>
    <label className="field"><span>Data</span><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></label>
    <label className="field"><span>Saiu de</span><select value={contaId} onChange={(e) => setContaId(e.target.value)}>{contas.map((conta) => <option key={conta.id} value={conta.id}>{conta.nome}</option>)}<option value="">Não lançar no Caixa</option></select></label>
    <label className="field fin-editor-largo"><span>Observação</span><input value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="Opcional" /></label>
    {erro && <Aviso tipo="error">{erro}</Aviso>}
    <div className="fin-editor-acoes"><span className="fin-espaco" /><button type="button" className="btn-ghost" onClick={aoCancelar}>Cancelar</button><button type="submit" className="btn-primary"><Icon name="check" size={14} /> Confirmar pagamento</button></div>
  </form>;
}

export function ComissoesPage() {
  const [competencia, setCompetencia] = useCompetencia();
  const { dados, erro, carregar } = useDados(async () => {
    const [comissoes, contas] = await Promise.all([api.comissoes(competencia), api.contas()]);
    return { ...comissoes, contas: contas.filter((c) => c.ativa) };
  }, competencia);
  const [pagando, setPagando] = useState(null);
  return <Moldura competencia={competencia} aoMudarMes={setCompetencia} erro={erro} carregando={!dados} aoImportar={carregar}>
    {dados && <>
      <section className="fin-comissao-hero card">
        <div><span className="eyebrow">COMISSÕES DO MÊS</span><Dinheiro valor={dados.resumo.gerado} tamanho="xl" /><p>Apuradas automaticamente pelos carregamentos, sem redigitação.</p></div>
        <dl><div><dt>Pago</dt><dd className="pago">{brl(dados.resumo.pago)}</dd></div><div><dt>Pendente</dt><dd className="pendente">{brl(dados.resumo.pendente)}</dd></div><div><dt>Cargas</dt><dd>{dados.resumo.cargas}</dd></div><div><dt>Toneladas</dt><dd>{toneladas(dados.resumo.toneladas)}</dd></div><div><dt>Média</dt><dd>{dados.resumo.media_ton === null ? "—" : `${brl(dados.resumo.media_ton)}/t`}</dd></div></dl>
      </section>
      <div className="fin-comissao-grupos">
        {dados.grupos.map((grupo) => <section className="card fin-comissao-grupo" key={grupo.beneficiario}>
          <header><div><span className="eyebrow">BENEFICIÁRIO</span><h3>{grupo.beneficiario}</h3><small>{grupo.cargas} cargas · {toneladas(grupo.toneladas)} · média {brl(grupo.media_ton)}/t</small></div><div className="fin-comissao-saldos"><span>Gerado <b>{brl(grupo.gerado)}</b></span><span>Pago <b>{brl(grupo.pago)}</b></span><span className={grupo.pendente > 0 ? "pendente" : "pago"}>Pendente <b>{brl(grupo.pendente)}</b></span></div>{grupo.pendente > 0 && <button type="button" className="btn-primary" onClick={() => setPagando(pagando === grupo.beneficiario ? null : grupo.beneficiario)}><Icon name="wallet" size={14} /> Registrar pagamento</button>}</header>
          {pagando === grupo.beneficiario && <FormPagamentoComissao grupo={grupo} contas={dados.contas} aoCancelar={() => setPagando(null)} aoSalvar={async (payload) => { await api.pagarComissao({ ...payload, competencia }); setPagando(null); await carregar(); }} />}
          <span className="fin-progresso"><i style={{ width: `${grupo.gerado ? Math.min(100, (grupo.pago / grupo.gerado) * 100) : 0}%` }} /></span>
        </section>)}
      </div>
      <section className="card fin-faturas fin-comissao-detalhes"><header className="fin-extrato-topo"><div><h3>Comissões por carregamento</h3><p>Dados puxados do próprio controle financeiro</p></div></header>
        {dados.linhas.length === 0 ? <div className="fin-sem-itens"><Icon name="users" size={22} /><p>Nenhuma comissão apurada neste mês.</p></div> : <div className="fin-faturas-tabela"><table><thead><tr><th>Data</th><th>CT-e / Motorista</th><th>Destino</th><th>Peso</th><th>Frete motorista</th><th>Comissão/t</th><th>Comissão total</th><th>Beneficiário</th></tr></thead><tbody>{dados.linhas.map((linha) => <tr key={linha.id}><td>{linha.data ? new Date(`${linha.data}T12:00:00`).toLocaleDateString("pt-BR") : "—"}</td><td><strong>{linha.cte || "Sem CT-e"}</strong><br /><small>{linha.motorista}</small></td><td>{linha.destino || "—"}</td><td>{toneladas(linha.peso)}</td><td>{brl(linha.frete_motorista)}</td><td>{linha.comissao_ton === null ? "—" : brl(linha.comissao_ton)}</td><td><Dinheiro valor={linha.comissao} tamanho="xs" /></td><td>{linha.beneficiario}</td></tr>)}</tbody></table></div>}
      </section>
      {dados.pagamentos.length > 0 && <section className="card fin-comissao-historico"><header className="fin-extrato-topo"><div><h3>Pagamentos realizados</h3><p>Baixas registradas no mês</p></div></header><ul>{dados.pagamentos.map((pagamento) => <li key={pagamento.id}><div><strong>{pagamento.beneficiario}</strong><small>{new Date(`${pagamento.pago_em}T12:00:00`).toLocaleDateString("pt-BR")}{pagamento.conta ? ` · ${pagamento.conta}` : ""}{pagamento.observacao ? ` · ${pagamento.observacao}` : ""}</small></div><Dinheiro valor={pagamento.valor} tamanho="xs" /><button type="button" className="btn-ghost perigo" onClick={async () => { await api.desfazerComissao(pagamento.id); await carregar(); }}>Desfazer</button></li>)}</ul></section>}
    </>}
  </Moldura>;
}

// Divida nao e do mes: sem o seletor de mes.
export function DividasPage() {
  const { dados, erro, carregar } = useDados(() => api.dividas(), "dividas");
  return (
    <Moldura erro={erro} carregando={!dados} aoImportar={carregar}>
      {dados && <Dividas dividas={dados} recarregar={carregar} />}
    </Moldura>
  );
}
