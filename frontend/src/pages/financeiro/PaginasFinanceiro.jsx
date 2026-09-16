import { useCallback, useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
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

function useCompetencia() {
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

function useDados(buscar, chave) {
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

function Moldura({ competencia, aoMudarMes, erro, carregando, aoImportar, children }) {
  const [importando, setImportando] = useState(false);
  return (
    <div className="ops-page fin-pagina">
      <div className="fin-barra">
        {competencia && <NavegadorMes competencia={competencia} aoMudar={aoMudarMes} />}
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
      const [resultado, despesas] = await Promise.all([api.resultado(competencia), api.despesas(competencia)]);
      return { resultado, despesas };
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

// Divida nao e do mes: sem o seletor de mes.
export function DividasPage() {
  const { dados, erro, carregar } = useDados(() => api.dividas(), "dividas");
  return (
    <Moldura erro={erro} carregando={!dados} aoImportar={carregar}>
      {dados && <Dividas dividas={dados} recarregar={carregar} />}
    </Moldura>
  );
}

// Endereco da versao com tudo numa tela so (?aba=...).
const DESTINO_ANTIGO = {
  "gastos-empresa": "/financeiro/gastos",
  "gastos-pessoais": "/financeiro/gastos?aba=pessoal",
  precificacao: "/financeiro/precificacao",
  pagamentos: "/financeiro/pagamentos",
  dividas: "/financeiro/dividas",
};

export function RedirecionarCarregamentos() {
  const [busca] = useSearchParams();
  return <Navigate to={DESTINO_ANTIGO[busca.get("aba")] || "/financeiro/lucro-bruto"} replace />;
}
