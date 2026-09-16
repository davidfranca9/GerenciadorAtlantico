import { useEffect, useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { financeiro as api } from "../../api/client";
import Icon from "../../components/Icon";
import { Aviso, Dinheiro, Modal } from "./comum";
import { brl, diaCurto, nomeCompetencia, toneladas } from "./formato";
import { Moldura, useCompetencia, useDados } from "./PaginasFinanceiro";
import { Composicao, EditorCarregamento, saudeMargem } from "./ResultadoPage";

// As colunas de dinheiro da aba LUCRO BRUTO: total da carga e o valor por tonelada.
const COLUNAS = [
  { chave: "frete_empresa", rotulo: "Frete cobrado" },
  { chave: "frete_motorista", rotulo: "Motorista" },
  { chave: "agenciamento", rotulo: "Agenciamento" },
  { chave: "comissao", rotulo: "Comissão" },
];

const ORDENS = [
  { valor: "recentes", rotulo: "Mais recentes" },
  { valor: "sobra", rotulo: "Maior sobra" },
  { valor: "margem", rotulo: "Menor sobra por tonelada" },
];

// Enderecos da versao em que tudo ficava numa tela so (?aba=...).
const DESTINO_ANTIGO = {
  "lucro-bruto": "/financeiro/lucro-bruto",
  "gastos-empresa": "/financeiro/gastos",
  "gastos-pessoais": "/financeiro/gastos?aba=pessoal",
  precificacao: "/financeiro/precificacao",
  pagamentos: "/financeiro/pagamentos",
  dividas: "/financeiro/dividas",
};

function semAcento(texto) {
  return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// Le o mes no Bsoft, mostra o que entraria e so grava quando confirmar.
function PuxarDoBsoft({ competencia, aoFechar, aoTrazer }) {
  const [previa, setPrevia] = useState(null);
  const [feito, setFeito] = useState(null);
  const [erro, setErro] = useState("");
  const [trazendo, setTrazendo] = useState(false);
  const mes = nomeCompetencia(competencia).toLowerCase();

  useEffect(() => {
    let vivo = true;
    api.puxarDoBsoft(competencia, false)
      .then((r) => vivo && setPrevia(r))
      .catch((e) => vivo && setErro(e.message));
    return () => { vivo = false; };
  }, [competencia]);

  async function trazer() {
    setTrazendo(true);
    setErro("");
    try {
      const r = await api.puxarDoBsoft(competencia, true);
      setFeito(r);
      aoTrazer();
    } catch (e) {
      setErro(e.message);
    } finally {
      setTrazendo(false);
    }
  }

  const r = feito || previa;
  return (
    <Modal titulo="Puxar carregamentos do Bsoft" subtitulo={`CT-es e contratos de frete de ${mes}. Nada é alterado no Bsoft.`} aoFechar={aoFechar} largura={720}>
      {!r && !erro && <Aviso>Lendo os CT-es de {mes} no Bsoft. Pode levar alguns segundos...</Aviso>}
      {erro && <Aviso tipo="error">{erro}</Aviso>}
      {r && (
        <div className="fin-previa">
          <p className="fin-previa-titulo">
            No Bsoft: <strong>{r.ctes_no_bsoft} CT-es</strong> em <strong>{r.cargas_no_bsoft} cargas</strong>.{" "}
            {feito ? "Trazidas:" : "Vão entrar:"} <strong>{r.novos.length} {r.novos.length === 1 ? "carga nova" : "cargas novas"}</strong>
            {r.atualizados.length > 0 && `, ${r.atualizados.length} atualizada(s)`}
            {r.ja_existiam > 0 && ` · ${r.ja_existiam} já estavam no controle`}.
          </p>
          {r.sem_contrato > 0 && (
            <Aviso tipo="warning">{r.sem_contrato} {r.sem_contrato === 1 ? "carga ainda não tem" : "cargas ainda não têm"} contrato de frete no Bsoft: o frete do motorista fica para completar.</Aviso>
          )}
          {r.divergencias.length > 0 && (
            <>
              <p className="fin-previa-titulo">Cargas da planilha com valor diferente do Bsoft (o controle não foi alterado):</p>
              <ul className="fin-conferido">
                {r.divergencias.map((d) => (
                  <li key={d.ctes} className="diverge">
                    <span>CT-e {d.ctes} · {d.motorista}</span>
                    <span className="fin-conferido-valores">
                      {Object.entries(d.diferencas).map(([campo, v]) => (
                        <small key={campo}>{campo}: controle {campo === "peso" ? toneladas(v.controle) : brl(v.controle)} · Bsoft {campo === "peso" ? toneladas(v.bsoft) : brl(v.bsoft)}</small>
                      ))}
                    </span>
                    <Icon name="alert" size={15} />
                  </li>
                ))}
              </ul>
            </>
          )}
          {!feito && r.novos.length > 0 && (
            <ul className="fin-previa-lista fin-previa-cargas">
              {r.novos.map((c) => (
                <li key={c.ctes}>
                  <span>{c.data_emissao ? diaCurto(c.data_emissao) : "—"}</span>
                  <span><b>{c.motorista || "Sem motorista"}</b> · CT-e {c.ctes} · {c.fabrica} → {c.destino}{c.cancelado ? " · cancelado" : ""}</span>
                  <span>{toneladas(c.peso)} · {brl(c.frete_empresa)}{c.frete_motorista !== null ? ` · motorista ${brl(c.frete_motorista)}` : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <footer className="fin-modal-rodape">
        <button type="button" className="btn-secondary" onClick={aoFechar}>{feito ? "Fechar" : "Cancelar"}</button>
        {!feito && (
          <button type="button" className="btn-primary" disabled={!previa || trazendo || (!previa.novos.length && !previa.atualizados.length)} onClick={trazer}>
            {trazendo ? "Trazendo..." : previa && previa.novos.length ? `Trazer ${previa.novos.length} ${previa.novos.length === 1 ? "carga" : "cargas"}` : "Nada novo"}
          </button>
        )}
      </footer>
    </Modal>
  );
}

function LinhaCarregamento({ carga, aberto, aoAbrir, children }) {
  const t = carga.totais;
  const rota = [carga.fabrica, carga.destino].filter(Boolean).join(" → ");
  return (
    <li className={`fin-linha-carga ${carga.cancelado ? "cancelado" : ""} ${aberto ? "aberto" : ""}`}>
      <button type="button" className="fin-linha-carga-botao" onClick={aoAbrir} aria-expanded={aberto}>
        <span className="fin-carga-data">{carga.data_emissao ? diaCurto(carga.data_emissao) : "—"}</span>
        <span className="fin-linha-carga-quem">
          <strong>
            {carga.cancelado ? "Cancelado" : carga.motorista || "Sem motorista"}
            {carga.a_completar && <em className="fin-tag-completar" title="Veio do Bsoft: falta agenciamento, comissão e contratante">a completar</em>}
          </strong>
          <small>{[carga.ctes && `CT-e ${carga.ctes}`, rota, carga.cliente && `cliente ${carga.cliente}`, carga.contratante].filter(Boolean).join(" · ")}</small>
          {!carga.cancelado && <Composicao totais={t} />}
        </span>
        <span className="fin-linha-carga-custos">
          <span className="fin-col peso" data-rotulo="Peso">
            <b>{carga.cancelado ? "—" : toneladas(carga.peso)}</b>
          </span>
          {COLUNAS.map((coluna) => (
            <span key={coluna.chave} className={`fin-col ${coluna.chave}`} data-rotulo={coluna.rotulo}>
              {carga.cancelado ? <b>—</b> : (
                <>
                  <Dinheiro valor={t[coluna.chave]} tamanho="xs" />
                  <small>{carga.peso ? `${brl(t[coluna.chave] / carga.peso)}/t` : ""}</small>
                </>
              )}
            </span>
          ))}
        </span>
        <span className="fin-col sobra" data-rotulo="Sobra">
          {carga.cancelado ? <em>cancelado</em> : (
            <>
              <Dinheiro valor={t.liquido} tamanho="s" />
              <b className={`fin-margem ${saudeMargem(t.por_tonelada)}`}>{brl(t.por_tonelada)}/t</b>
            </>
          )}
        </span>
      </button>
      {children}
    </li>
  );
}

function ListaCarregamentos() {
  const [competencia, setCompetencia] = useCompetencia();
  const [todosOsMeses, setTodosOsMeses] = useState(false);
  const chave = todosOsMeses ? "todos" : competencia;
  const { dados, erro, carregar } = useDados(() => api.carregamentos(todosOsMeses ? undefined : competencia), chave);
  const [termo, setTermo] = useState("");
  const [fabrica, setFabrica] = useState("");
  const [contratante, setContratante] = useState("");
  const [ordem, setOrdem] = useState("recentes");
  const [abertoId, setAbertoId] = useState(null);
  const [puxando, setPuxando] = useState(false);

  const cargas = dados?.carregamentos || [];
  const fabricas = [...new Set(cargas.map((c) => c.fabrica).filter(Boolean))].sort();
  const contratantes = [...new Set(cargas.map((c) => c.contratante).filter(Boolean))].sort();

  const filtradas = useMemo(() => {
    const procurado = semAcento(termo).trim();
    const lista = cargas.filter((c) => {
      if (fabrica && c.fabrica !== fabrica) return false;
      if (contratante && c.contratante !== contratante) return false;
      if (!procurado) return true;
      return semAcento(`${c.motorista} ${c.ctes} ${c.destino} ${c.fabrica} ${c.contratante}`).includes(procurado);
    });
    if (ordem === "sobra") lista.sort((a, b) => (a.cancelado - b.cancelado) || b.totais.liquido - a.totais.liquido);
    if (ordem === "margem") {
      lista.sort((a, b) => (a.cancelado - b.cancelado) || (a.totais.por_tonelada ?? Infinity) - (b.totais.por_tonelada ?? Infinity));
    }
    return lista;
  }, [cargas, termo, fabrica, contratante, ordem]);

  const validas = filtradas.filter((c) => !c.cancelado);
  const soma = (campo) => validas.reduce((total, c) => total + c.totais[campo], 0);
  const peso = validas.reduce((total, c) => total + c.peso, 0);
  const sobra = soma("liquido");

  // Todos os meses na ordem de data: separa por mes, com o total de cada um.
  const grupos = [];
  for (const carga of filtradas) {
    const chaveGrupo = todosOsMeses && ordem === "recentes" ? carga.competencia : "lista";
    let grupo = grupos.find((g) => g.chave === chaveGrupo);
    if (!grupo) {
      grupo = { chave: chaveGrupo, cargas: [] };
      grupos.push(grupo);
    }
    grupo.cargas.push(carga);
  }

  const filtrando = termo || fabrica || contratante;

  return (
    <Moldura
      competencia={todosOsMeses ? null : competencia}
      aoMudarMes={setCompetencia}
      erro={erro}
      carregando={!dados}
      aoImportar={carregar}
      extras={(
        <button type="button" className={`btn-secondary ${todosOsMeses ? "fin-botao-ativo" : ""}`} aria-pressed={todosOsMeses} onClick={() => { setTodosOsMeses(!todosOsMeses); setAbertoId(null); }}>
          <Icon name="calendar" size={15} /> {todosOsMeses ? "Ver um mês" : "Todos os meses"}
        </button>
      )}
    >
      {dados && (
        <>
          <section className="fin-resumo-cargas" aria-label="Resumo das cargas listadas">
            <div><span>Cargas</span><strong>{validas.length}</strong><small>{filtradas.length - validas.length ? `+ ${filtradas.length - validas.length} ${filtradas.length - validas.length === 1 ? "cancelada" : "canceladas"}` : todosOsMeses ? "todos os meses" : nomeCompetencia(competencia)}</small></div>
            <div><span>Toneladas</span><strong>{toneladas(peso)}</strong><small>{validas.length ? `${toneladas(peso / validas.length)} por carga` : ""}</small></div>
            <div><span>Frete cobrado</span><Dinheiro valor={soma("frete_empresa")} tamanho="m" /><small>{peso ? `${brl(soma("frete_empresa") / peso)}/t` : ""}</small></div>
            <div><span>Custos da carga</span><Dinheiro valor={soma("frete_motorista") + soma("agenciamento") + soma("comissao")} tamanho="m" /><small>motorista, agenciamento e comissão</small></div>
            <div className="destaque"><span>Sobra</span><Dinheiro valor={sobra} tamanho="m" /><small>{peso ? <b className={`fin-margem ${saudeMargem(sobra / peso)}`}>{brl(sobra / peso)}/t</b> : ""}</small></div>
          </section>

          <div className="fin-filtros-cargas">
            <label className="fin-busca">
              <Icon name="search" size={14} />
              <input value={termo} onChange={(e) => setTermo(e.target.value)} placeholder="Motorista, CT-e ou destino" aria-label="Buscar carregamento" />
            </label>
            {fabricas.length > 1 && (
              <div className="fin-segmentado pequeno" role="group" aria-label="Fábrica">
                <button type="button" className={!fabrica ? "ativo" : ""} onClick={() => setFabrica("")}>Todas</button>
                {fabricas.map((f) => <button key={f} type="button" className={fabrica === f ? "ativo" : ""} onClick={() => setFabrica(fabrica === f ? "" : f)}>{f}</button>)}
              </div>
            )}
            {contratantes.length > 1 && (
              <select className="fin-select-pequeno" value={contratante} onChange={(e) => setContratante(e.target.value)} aria-label="Contratante">
                <option value="">Todos os contratantes</option>
                {contratantes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            )}
            <select className="fin-select-pequeno" value={ordem} onChange={(e) => setOrdem(e.target.value)} aria-label="Ordenar">
              {ORDENS.map((o) => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
            </select>
            {filtrando && <button type="button" className="fin-link" onClick={() => { setTermo(""); setFabrica(""); setContratante(""); }}>Limpar filtros</button>}
            <span className="fin-espaco" />
            <button
              type="button" className="btn-secondary" disabled={todosOsMeses} onClick={() => setPuxando(true)}
              title={todosOsMeses ? "Escolha um mês para puxar do Bsoft" : "Traz os CT-es e contratos de frete do mês"}
            >
              <Icon name="refresh" size={15} /> Puxar do Bsoft
            </button>
            <button type="button" className="btn-primary" onClick={() => setAbertoId(abertoId === "novo" ? null : "novo")}><Icon name="plus" size={15} /> Carregamento</button>
          </div>

          <section className="card fin-tabela-cargas">
            <div className="fin-cabecalho-cargas" aria-hidden="true">
              <span>Data</span><span>Carga</span>
              <span className="fin-linha-carga-custos"><span>Peso</span>{COLUNAS.map((c) => <span key={c.chave}>{c.rotulo}</span>)}</span>
              <span>Sobra</span>
            </div>
            {abertoId === "novo" && (
              <div className="fin-linha-carga aberto">
                <EditorCarregamento
                  competencia={competencia}
                  aoFechar={() => setAbertoId(null)}
                  aoSalvar={async (p) => { await api.criarCarregamento(p); setAbertoId(null); await carregar(); }}
                />
              </div>
            )}
            {filtradas.length === 0 ? (
              <div className="fin-sem-itens">
                <Icon name="truck" size={22} />
                <p>{cargas.length ? "Nenhum carregamento com esses filtros." : `Nenhum carregamento ${todosOsMeses ? "cadastrado" : `em ${nomeCompetencia(competencia).toLowerCase()}`}. Use "Puxar do Bsoft" para trazer os CT-es do mês, importe a planilha ou lance a carga.`}</p>
              </div>
            ) : grupos.map((grupo) => {
              const doMes = grupo.cargas.filter((c) => !c.cancelado);
              const pesoMes = doMes.reduce((t, c) => t + c.peso, 0);
              return (
                <div key={grupo.chave}>
                  {grupo.chave !== "lista" && (
                    <h4 className="fin-mes-cargas">
                      <span>{nomeCompetencia(grupo.chave)}</span>
                      <span>{doMes.length} {doMes.length === 1 ? "carga" : "cargas"} · {toneladas(pesoMes)} · sobra {brl(doMes.reduce((t, c) => t + c.totais.liquido, 0))}</span>
                    </h4>
                  )}
                  <ul>
                    {grupo.cargas.map((carga) => (
                      <LinhaCarregamento key={carga.id} carga={carga} aberto={abertoId === carga.id} aoAbrir={() => setAbertoId(abertoId === carga.id ? null : carga.id)}>
                        {abertoId === carga.id && (
                          <EditorCarregamento
                            competencia={carga.competencia}
                            carregamento={carga}
                            aoFechar={() => setAbertoId(null)}
                            aoSalvar={async (p) => { await api.atualizarCarregamento(carga.id, p); setAbertoId(null); await carregar(); }}
                            aoExcluir={async () => { await api.excluirCarregamento(carga.id); setAbertoId(null); await carregar(); }}
                          />
                        )}
                      </LinhaCarregamento>
                    ))}
                  </ul>
                </div>
              );
            })}
          </section>
          {puxando && <PuxarDoBsoft competencia={competencia} aoFechar={() => setPuxando(false)} aoTrazer={carregar} />}
        </>
      )}
    </Moldura>
  );
}

export default function CarregamentosPage() {
  const [busca] = useSearchParams();
  const antiga = busca.get("aba");
  if (antiga) return <Navigate to={DESTINO_ANTIGO[antiga] || "/financeiro/lucro-bruto"} replace />;
  return <ListaCarregamentos />;
}
