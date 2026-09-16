import { Fragment, useEffect, useMemo, useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";
import { formatCPF, formatDateInput, formatNome, formatPhone, formatPlaca } from "../utils/format";
import { MODELOS_VEICULO } from "../utils/vehicleCategory";
import EmailMotoristaPanel from "../components/EmailMotoristaPanel";
import Icon from "../components/Icon";

const STATUS_OPTIONS = ["Aguardando Agendamento", "Agendado", "Cancelado", "Carregou"];
const ITEM_VAZIO = { pedidoId: null, pedido: "", cliente: "", produto: "", cidade: "", embalagem: "", toneladas: "", toneladasMax: 0 };
const OC_ITEM_VAZIO = { contrato: "", cliente: "", produto: "", cidade: "", embalagem: "", toneladas: "" };
const SUPPLIER_LABEL = { AFL: "Fertimaxi", HERINGER: "Heringer" };

function templateFromSupplierLabel(label) {
  return label === "Heringer" ? "HERINGER" : "AFL";
}

function parseNumero(texto) {
  const num = parseFloat(String(texto ?? "").replace(",", "."));
  return Number.isFinite(num) ? num : 0;
}

function formatTon(valor) {
  return parseNumero(valor).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

const DIAS_SEMANA_LABEL = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

function formatarDataBR(date) {
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const yyyy = date.getFullYear();
  return `${dd}/${mm}/${yyyy}`;
}

function gerarGradeDoMes(referencia) {
  const ano = referencia.getFullYear();
  const mes = referencia.getMonth();
  const primeiroDia = new Date(ano, mes, 1);
  const diaSemanaPrimeiro = (primeiroDia.getDay() + 6) % 7; // 0 = segunda
  const inicioGrade = new Date(ano, mes, 1 - diaSemanaPrimeiro);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(inicioGrade);
    d.setDate(inicioGrade.getDate() + i);
    return d;
  });
}

function DataAgendadaCell({ agendamento, onSalvo }) {
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState(agendamento.data_agendada || "");
  const [salvando, setSalvando] = useState(false);

  async function salvar() {
    setSalvando(true);
    try {
      await api.confirmarDataAgendada(agendamento.id, valor);
      setEditando(false);
      onSalvo();
    } catch {
      // erro fica visivel na lista ao recarregar
    } finally {
      setSalvando(false);
    }
  }

  if (editando) {
    return (
      <div style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 190 }}>
        <input
          value={valor}
          onChange={(e) => setValor(formatDateInput(e.target.value))}
          placeholder="dd/mm/aaaa"
          style={{ height: 32, width: 110 }}
          autoFocus
        />
        <button className="btn-primary" style={{ minHeight: 32, padding: "0 10px" }} disabled={salvando} onClick={salvar}>
          {salvando ? "..." : "OK"}
        </button>
        <button className="btn-ghost" style={{ minHeight: 32, padding: "0 8px" }} onClick={() => setEditando(false)}>
          ✕
        </button>
      </div>
    );
  }

  return (
    <button
      className="btn-ghost"
      style={{ minHeight: 30, padding: "0 8px", color: agendamento.data_agendada ? "var(--accent-glow)" : "var(--muted-soft)" }}
      onClick={() => { setValor(agendamento.data_agendada || ""); setEditando(true); }}
      title={agendamento.agendamento_confirmado_por ? `Confirmado por ${agendamento.agendamento_confirmado_por}` : "Clique para informar a data confirmada"}
    >
      {agendamento.data_agendada || "aguardando"}
    </button>
  );
}

// Horario gravado em UTC (sem fuso) -> hora local.
function formatarQuando(iso) {
  if (!iso) return "";
  const data = new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(data.getTime())
    ? iso
    : data.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function semAcentoBusca(texto) {
  return String(texto ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}

// Tudo que da pra procurar num agendamento: motorista, CPF, placas, datas,
// fornecedor, status, observacoes e os itens (pedido, cliente, produto,
// cidade). A comparacao ignora acento, caixa e pontuacao - "abc1d23" acha
// "ABC-1D23" e "40947" acha "040947".
function agendamentoCombina(a, termo) {
  const texto = semAcentoBusca([
    a.id, a.supplier, a.loading_date, a.data_agendada, a.driver_name, a.driver_cpf,
    a.plate_cavalo, a.plate_carreta1, a.plate_carreta2, a.modelo_veiculo, a.status, a.observacoes,
    ...(a.itens || []).flatMap((it) => [it.pedido, it.cliente, it.produto, it.cidade]),
  ].join(" | "));
  const procurado = semAcentoBusca(termo).trim();
  if (!procurado) return true;
  if (texto.includes(procurado)) return true;
  const compacto = procurado.replace(/[^A-Z0-9]/g, "");
  return Boolean(compacto) && texto.replace(/[^A-Z0-9|]/g, "").includes(compacto);
}

export default function AgendamentosPage() {
  const [agendamentos, setAgendamentos] = useState([]);
  const [filtroStatus, setFiltroStatus] = useState("");
  const [busca, setBusca] = useState("");
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [supplier, setSupplier] = useState("");
  const [loadingDate, setLoadingDate] = useState("");
  const [driverName, setDriverName] = useState("");
  const [plateCavalo, setPlateCavalo] = useState("");
  const [itens, setItens] = useState([{ ...ITEM_VAZIO }]);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState("lista");
  const [mesReferencia, setMesReferencia] = useState(() => { const d = new Date(); d.setDate(1); return d; });
  const [diaSelecionado, setDiaSelecionado] = useState(null);
  const [pedidosDisponiveis, setPedidosDisponiveis] = useState([]);

  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const [docGerandoId, setDocGerandoId] = useState(null);
  const [verAbertoId, setVerAbertoId] = useState(null);
  const [motoristaAbertoId, setMotoristaAbertoId] = useState(null);
  const [pedidosEdicao, setPedidosEdicao] = useState([]);
  const [avisoEmail, setAvisoEmail] = useState("");

  async function carregar() {
    setLoading(true);
    try {
      const data = await api.listarAgendamentos(filtroStatus || undefined);
      setAgendamentos(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroStatus]);

  // Na agenda vale a data confirmada pelo fornecedor; enquanto ela nao vem,
  // o agendamento aparece na data que foi solicitada.
  function dataEfetiva(a) {
    return a.data_agendada || a.loading_date;
  }

  const agendamentosPorDia = useMemo(() => {
    const mapa = {};
    for (const a of agendamentos) {
      const dia = a.data_agendada || a.loading_date;
      if (!dia) continue;
      (mapa[dia] ||= []).push(a);
    }
    return mapa;
  }, [agendamentos]);

  const gradeDoMes = useMemo(() => gerarGradeDoMes(mesReferencia), [mesReferencia]);
  const hojeStr = formatarDataBR(new Date());

  function mudarMes(delta) {
    setMesReferencia((prev) => {
      const d = new Date(prev);
      d.setMonth(d.getMonth() + delta);
      return d;
    });
    setDiaSelecionado(null);
  }

  function irParaHoje() {
    const hoje = new Date();
    hoje.setDate(1);
    setMesReferencia(hoje);
    setDiaSelecionado(hojeStr);
  }

  const agendamentosExibidos = (viewMode === "agenda" && diaSelecionado
    ? agendamentos.filter((a) => dataEfetiva(a) === diaSelecionado)
    : agendamentos
  ).filter((a) => agendamentoCombina(a, busca));

  useEffect(() => {
    if (showForm) {
      api.listarPedidos().then(setPedidosDisponiveis).catch((err) => setError(err.message));
    }
  }, [showForm]);

  function selecionarPedidoNoItem(idx, pedidoId) {
    const pedido = pedidosDisponiveis.find((p) => String(p.id) === pedidoId);
    setItens((prev) => prev.map((it, i) => (i !== idx ? it : pedido ? {
      ...it,
      pedidoId: pedido.id,
      pedido: pedido.contrato,
      cliente: pedido.cliente,
      produto: pedido.produto,
      cidade: pedido.cidade,
      embalagem: pedido.embalagem,
      toneladas: String(pedido.toneladas_restante),
      toneladasMax: pedido.toneladas_restante,
    } : { ...ITEM_VAZIO })));
  }

  function updateItemToneladas(idx, texto) {
    setItens((prev) => prev.map((it, i) => {
      if (i !== idx) return it;
      const max = it.toneladasMax;
      const valor = parseNumero(texto);
      const limitado = texto !== "" && max > 0 && valor > max ? it.toneladas : texto;
      return { ...it, toneladas: limitado };
    }));
  }

  async function handleCriar(e) {
    e.preventDefault();
    setError("");
    try {
      await api.criarAgendamento({
        supplier,
        loading_date: loadingDate,
        driver_name: driverName,
        plate_cavalo: plateCavalo,
        itens: itens.map((it) => ({
          pedido: it.pedido,
          cliente: it.cliente,
          produto: it.produto,
          cidade: it.cidade,
          embalagem: it.embalagem,
          toneladas: parseFloat(String(it.toneladas).replace(",", ".")) || 0,
          pedido_id: it.pedidoId || null,
        })),
      });
      setShowForm(false);
      setSupplier("");
      setLoadingDate("");
      setDriverName("");
      setPlateCavalo("");
      setItens([{ ...ITEM_VAZIO }]);
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleStatus(id, status) {
    try {
      await api.atualizarStatusAgendamento(id, status);
      carregar();
    } catch (err) {
      setError(err.message);
    }
  }

  async function abrirEdicao(a) {
    setEditError("");
    setEditId(a.id);
    setEditForm(null);
    setEditLoading(true);
    try {
      const [full, listaPedidos] = await Promise.all([
        api.obterAgendamento(a.id),
        api.listarPedidos(true).catch(() => []),
      ]);
      setPedidosEdicao(listaPedidos);
      setEditForm({
        template: templateFromSupplierLabel(full.supplier),
        loading_date: full.loading_date || "",
        driver_name: full.driver_name || "",
        driver_cpf: full.driver_cpf || "",
        driver_phone: full.driver_phone || "",
        cnh: full.cnh || "",
        plate_cavalo: full.plate_cavalo || "",
        plate_carreta1: full.plate_carreta1 || "",
        plate_carreta2: full.plate_carreta2 || "",
        modelo_veiculo: full.modelo_veiculo || "",
        observacoes: full.observacoes || "",
        itens: full.itens.length
          ? full.itens.map((it) => ({
              contrato: it.pedido || "",
              cliente: it.cliente || "",
              produto: it.produto || "",
              cidade: it.cidade || "",
              embalagem: it.embalagem || "",
              toneladas: String(it.toneladas ?? ""),
              pedido_id: it.pedido_id ?? null,
              // O que o item ja ocupava: volta a ficar disponivel pra ele mesmo.
              pedidoOriginalId: it.pedido_id ?? null,
              toneladasOriginal: parseNumero(it.toneladas),
            }))
          : [{ ...OC_ITEM_VAZIO }],
      });
    } catch (err) {
      setEditError(err.message);
    } finally {
      setEditLoading(false);
    }
  }

  function fecharEdicao() {
    setEditId(null);
    setEditForm(null);
    setEditError("");
  }

  async function handleExcluir(a) {
    const rotulo = a.driver_name || a.observacoes || `#${a.id}`;
    if (!window.confirm(`Excluir o agendamento de "${rotulo}" (${a.loading_date})? Essa ação não pode ser desfeita.`)) return;
    setError("");
    try {
      await api.excluirAgendamento(a.id);
      if (editId === a.id) fecharEdicao();
      setAgendamentos((prev) => prev.filter((x) => x.id !== a.id));
    } catch (err) {
      setError(err.message);
    }
  }

  function updateEditField(field, value) {
    setEditForm((prev) => ({ ...prev, [field]: value }));
  }

  // Tonelada que o item pode usar do pedido: o saldo restante, mais o que
  // ele mesmo ja ocupava (senao editar um item que usou o pedido inteiro
  // nao deixaria nem manter o valor).
  function disponivelNaEdicao(it) {
    const pedido = pedidosEdicao.find((p) => String(p.id) === String(it.pedido_id));
    if (!pedido) return null;
    const proprio = String(it.pedidoOriginalId) === String(it.pedido_id) ? it.toneladasOriginal || 0 : 0;
    return pedido.toneladas_restante + proprio;
  }

  function selecionarPedidoNaEdicao(idx, pedidoId) {
    const pedido = pedidosEdicao.find((p) => String(p.id) === String(pedidoId));
    setEditForm((prev) => ({
      ...prev,
      itens: prev.itens.map((it, i) => {
        if (i !== idx) return it;
        if (!pedido) return { ...it, pedido_id: null };
        const voltouAoOriginal = String(it.pedidoOriginalId) === String(pedido.id);
        return {
          ...it,
          pedido_id: pedido.id,
          contrato: pedido.contrato,
          cliente: pedido.cliente,
          produto: pedido.produto,
          cidade: pedido.cidade,
          embalagem: pedido.embalagem,
          toneladas: voltouAoOriginal ? String(it.toneladasOriginal) : String(pedido.toneladas_restante),
        };
      }),
    }));
  }

  function updateEditItem(idx, field, value) {
    setEditForm((prev) => ({
      ...prev,
      // Mudou o numero ou o produto: o vinculo antigo nao vale mais, e o
      // backend acha o pedido certo pelo que foi digitado.
      itens: prev.itens.map((it, i) => (i === idx
        ? { ...it, [field]: value, ...(field === "contrato" || field === "produto" ? { pedido_id: null } : {}) }
        : it)),
    }));
  }

  async function salvarERegerar() {
    setEditSaving(true);
    setEditError("");
    try {
      const payload = {
        template: editForm.template,
        produtos: editForm.itens.filter((it) => it.pedido_id || String(it.contrato || "").trim()),
        cpf: editForm.driver_cpf,
        nome: editForm.driver_name,
        cnh: editForm.cnh,
        fone: editForm.driver_phone,
        placa1: editForm.plate_cavalo,
        placa2: editForm.plate_carreta1,
        placa3: editForm.plate_carreta2,
        modelo_veiculo: editForm.modelo_veiculo,
        data_carregamento: editForm.loading_date,
        observacoes: editForm.observacoes,
        agendamento_id: editId,
      };
      const result = await api.gerarOrdemColeta(payload);
      if (editForm.template !== "HERINGER") {
        await api.gerarAutorizacaoColeta({ ...payload, agendamento_id: result?.agendamentoId ?? editId });
      }
      fecharEdicao();
      carregar();
    } catch (err) {
      setEditError(err.message);
    } finally {
      setEditSaving(false);
    }
  }

  async function salvarDocumentos(a) {
    setError("");
    setDocGerandoId(a.id);
    try {
      const template = templateFromSupplierLabel(a.supplier);
      const payload = {
        template,
        produtos: a.itens.map((it) => ({
          contrato: it.pedido || "",
          cliente: it.cliente || "",
          produto: it.produto || "",
          cidade: it.cidade || "",
          embalagem: it.embalagem || "",
          toneladas: String(it.toneladas ?? ""),
          pedido_id: it.pedido_id ?? null,
        })),
        cpf: a.driver_cpf,
        nome: a.driver_name,
        cnh: a.cnh,
        fone: a.driver_phone,
        placa1: a.plate_cavalo,
        placa2: a.plate_carreta1,
        placa3: a.plate_carreta2,
        modelo_veiculo: a.modelo_veiculo || "",
        data_carregamento: a.loading_date,
        observacoes: a.observacoes,
        agendamento_id: a.id,
      };
      const result = await api.gerarOrdemColeta(payload);
      if (template !== "HERINGER") {
        await api.gerarAutorizacaoColeta({ ...payload, agendamento_id: result?.agendamentoId ?? a.id });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setDocGerandoId(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div className="pedidos-ordenacao-toggle">
          <button type="button" className={viewMode === "lista" ? "btn-primary" : "btn-secondary"} onClick={() => { setViewMode("lista"); setDiaSelecionado(null); }}>
            Lista
          </button>
          <button type="button" className={viewMode === "agenda" ? "btn-primary" : "btn-secondary"} onClick={() => setViewMode("agenda")}>
            Agenda
          </button>
        </div>
        <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancelar" : "+ Novo Agendamento"}
        </button>
      </div>

      {viewMode === "agenda" && (
        <div className="card agenda-card">
          <div className="agenda-header">
            <strong>{mesReferencia.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}</strong>
            <div className="agenda-nav">
              <button type="button" className="btn-secondary" onClick={() => mudarMes(-1)}>‹</button>
              <button type="button" className="btn-secondary" onClick={irParaHoje}>Hoje</button>
              <button type="button" className="btn-secondary" onClick={() => mudarMes(1)}>›</button>
            </div>
          </div>
          <div className="agenda-grid agenda-grid-header">
            {DIAS_SEMANA_LABEL.map((d) => <div key={d}>{d}</div>)}
          </div>
          <div className="agenda-grid">
            {gradeDoMes.map((dia) => {
              const chave = formatarDataBR(dia);
              const doMes = dia.getMonth() === mesReferencia.getMonth();
              const itensDoDia = agendamentosPorDia[chave] || [];
              const totalTons = itensDoDia.reduce((soma, a) => soma + (a.total_tons || 0), 0);
              return (
                <button
                  type="button"
                  key={chave}
                  className={`agenda-day ${doMes ? "" : "outro-mes"} ${chave === hojeStr ? "hoje" : ""} ${chave === diaSelecionado ? "selecionado" : ""}`}
                  onClick={() => setDiaSelecionado(chave === diaSelecionado ? null : chave)}
                >
                  <span className="agenda-day-number">{dia.getDate()}</span>
                  {itensDoDia.length > 0 && (
                    <div className="agenda-day-info">
                      <span className="agenda-day-count">{itensDoDia.length}</span>
                      <span className="agenda-day-tons">{formatTon(totalTons)}t</span>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          {diaSelecionado && (
            <div className="agenda-selecionado-bar">
              <span>Mostrando agendamentos de <strong>{diaSelecionado}</strong></span>
              <button type="button" className="btn-ghost" onClick={() => setDiaSelecionado(null)}>Limpar seleção</button>
            </div>
          )}
        </div>
      )}

      {showForm && (
        <form onSubmit={handleCriar} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="field-grid">
            <div className="field">
              <label>Fornecedor</label>
              <select value={supplier} onChange={(e) => setSupplier(e.target.value)} required>
                <option value="">Selecione</option>
                {Object.values(SUPPLIER_LABEL).map((label) => (
                  <option key={label} value={label}>{label}</option>
                ))}
              </select>
            </div>
            <DateField label="Data solicitada" value={loadingDate} onChange={setLoadingDate} />
            <div className="field">
              <label>Motorista</label>
              <input value={driverName} onChange={(e) => setDriverName(formatNome(e.target.value))} />
            </div>
            <div className="field">
              <label>Placa Cavalo</label>
              <input value={plateCavalo} onChange={(e) => setPlateCavalo(formatPlaca(e.target.value))} placeholder="ABC-1D23" />
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Pedido</th>
                <th>Cliente</th>
                <th>Produto</th>
                <th>Cidade/UF</th>
                <th>Toneladas</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {itens.map((it, idx) => (
                <tr key={idx}>
                  <td>
                    <select value={it.pedidoId ?? ""} onChange={(e) => selecionarPedidoNoItem(idx, e.target.value)}>
                      <option value="">Selecione um pedido</option>
                      {pedidosDisponiveis.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.novo ? "NOVO · " : ""}{p.contrato || "s/nº"} · {p.produto} · {formatTon(p.toneladas_restante)}t restantes
                        </option>
                      ))}
                    </select>
                  </td>
                  <td><input value={it.cliente} disabled /></td>
                  <td><input value={it.produto} disabled /></td>
                  <td><input value={it.cidade} disabled /></td>
                  <td>
                    <input
                      value={it.toneladas}
                      onChange={(e) => updateItemToneladas(idx, e.target.value)}
                      disabled={!it.pedidoId}
                      title={it.pedidoId ? `Máximo: ${formatTon(it.toneladasMax)}` : ""}
                    />
                  </td>
                  <td>
                    {itens.length > 1 && (
                      <button type="button" className="btn-secondary" onClick={() => setItens((prev) => prev.filter((_, i) => i !== idx))}>
                        Remover
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="btn-secondary" onClick={() => setItens((prev) => [...prev, { ...ITEM_VAZIO }])}>
            + Item
          </button>
          <button type="submit" className="btn-primary">Salvar Agendamento</button>
        </form>
      )}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 320px", maxWidth: 480 }}>
          <label>Buscar agendamento</label>
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Motorista, placa, cliente, pedido, produto ou cidade"
          />
        </div>
      <div className="field" style={{ maxWidth: 260 }}>
        <label>Filtrar por status</label>
        <select value={filtroStatus} onChange={(e) => setFiltroStatus(e.target.value)}>
          <option value="">Todos</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>
        {busca.trim() && (
          <span style={{ fontSize: 12.5, color: "var(--muted)", paddingBottom: 10 }}>
            {agendamentosExibidos.length} encontrado(s)
          </span>
        )}
      </div>

      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}
      {avisoEmail && <div className="inline-alert info">{avisoEmail}</div>}

      <div className="card" style={{ overflowX: "auto" }}>
        {/* Compacta pra caber em notebook (1366 px) sem rolar de lado: itens e
            toneladas numa coluna so, motorista com a acao dele na propria
            celula e as demais acoes como icones. */}
        <table className="tabela-agendamentos">
          <thead>
            <tr>
              <th>Fornecedor</th>
              <th>Solicitada</th>
              <th>Agendada</th>
              <th>Motorista</th>
              <th>Carga</th>
              <th>Observações</th>
              <th>Status</th>
              <th><span className="sr-only">Ações</span></th>
            </tr>
          </thead>
          <tbody>
            {agendamentosExibidos.map((a) => (
              <Fragment key={a.id}>
                <tr
                  className="clickable-row"
                  onClick={() => setVerAbertoId(verAbertoId === a.id ? null : a.id)}
                  title="Clique pra ver os itens agendados"
                >
                  <td>{a.supplier}</td>
                  <td>{a.loading_date}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <DataAgendadaCell agendamento={a} onSalvo={carregar} />
                  </td>
                  <td className="celula-motorista">
                    {a.driver_name && <span>{a.driver_name}</span>}
                    <button
                      className="link-motorista"
                      onClick={(e) => {
                        e.stopPropagation();
                        setMotoristaAbertoId(motoristaAbertoId === a.id ? null : a.id);
                      }}
                    >
                      {motoristaAbertoId === a.id ? "Fechar" : a.driver_name ? "Substituir motorista" : "+ Incluir motorista"}
                    </button>
                  </td>
                  <td className="celula-carga">
                    <strong>{a.total_tons} t</strong>
                    <span>{a.total_items} {Number(a.total_items) === 1 ? "item" : "itens"}</span>
                  </td>
                  <td style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.observacoes}>
                    {a.observacoes || "-"}
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <select value={a.status} onChange={(e) => handleStatus(a.id, e.target.value)}>
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="acoes-agendamento">
                      <button
                        className={`icon-btn${editId === a.id ? " ativo" : ""}`}
                        title={editId === a.id ? "Fechar edição" : "Editar"}
                        aria-label={editId === a.id ? "Fechar edição" : "Editar"}
                        onClick={() => (editId === a.id ? fecharEdicao() : abrirEdicao(a))}
                      >
                        <Icon name={editId === a.id ? "close" : "edit"} size={15} />
                      </button>
                      <button
                        className="icon-btn"
                        title={docGerandoId === a.id ? "Gerando documentos..." : "Salvar documentos"}
                        aria-label="Salvar documentos"
                        disabled={docGerandoId === a.id}
                        onClick={() => salvarDocumentos(a)}
                      >
                        <Icon name={docGerandoId === a.id ? "refresh" : "download"} size={15} />
                      </button>
                      <button className="icon-btn perigo" title="Excluir" aria-label="Excluir" onClick={() => handleExcluir(a)}>
                        <Icon name="trash" size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
                {motoristaAbertoId === a.id && (
                  <tr key={`${a.id}-motorista`}>
                    <td colSpan={8}>
                      <EmailMotoristaPanel
                        agendamento={a}
                        aoFechar={() => setMotoristaAbertoId(null)}
                        aoEnviar={(email) => {
                          setMotoristaAbertoId(null);
                          setAvisoEmail(`E-mail enviado: "${email.assunto}" para ${email.para.join(", ")}.`);
                          carregar();
                        }}
                      />
                    </td>
                  </tr>
                )}
                {verAbertoId === a.id && (
                  <tr key={`${a.id}-ver`}>
                    <td colSpan={8}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "10px 4px" }}>
                        <strong>Itens agendados</strong>
                        <table>
                          <thead>
                            <tr>
                              <th>Pedido</th>
                              <th>Cliente</th>
                              <th>Produto</th>
                              <th>Cidade</th>
                              <th>Embalagem</th>
                              <th>Toneladas</th>
                            </tr>
                          </thead>
                          <tbody>
                            {a.itens.map((it) => (
                              <tr key={it.id}>
                                <td>{it.pedido || "-"}</td>
                                <td>{it.cliente || "-"}</td>
                                <td>{it.produto || "-"}</td>
                                <td>{it.cidade || "-"}</td>
                                <td>{it.embalagem || "-"}</td>
                                <td>{formatTon(it.toneladas)}</td>
                              </tr>
                            ))}
                            {a.itens.length === 0 && (
                              <tr><td colSpan={6} style={{ color: "var(--muted)" }}>Nenhum item nesse agendamento.</td></tr>
                            )}
                          </tbody>
                        </table>
                        {(a.emails || []).length > 0 && (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                            <strong>E-mails de motorista</strong>
                            {a.emails.map((email, i) => (
                              <div key={i} style={{ fontSize: 12.5 }}>
                                {email.tipo === "inclusao" ? "Inclusão" : "Substituição"}
                                {email.teste ? " (teste)" : ""} · {formatarQuando(email.created_at)} · {email.motorista}
                                {email.motorista_anterior ? ` no lugar de ${email.motorista_anterior}` : ""} · para {email.destinatarios}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
                {editId === a.id && (
                  <tr key={`${a.id}-edit`}>
                    <td colSpan={8}>
                      {editLoading && <div style={{ padding: 12, color: "var(--muted)" }}>Carregando...</div>}
                      {!editLoading && editForm && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "12px 4px" }}>
                          <div className="field-grid">
                            <div className="field">
                              <label>Fornecedor</label>
                              <select value={editForm.template} onChange={(e) => updateEditField("template", e.target.value)}>
                                {Object.entries(SUPPLIER_LABEL).map(([code, label]) => (
                                  <option key={code} value={code}>{label}</option>
                                ))}
                              </select>
                            </div>
                            <DateField label="Data de Carregamento" value={editForm.loading_date} onChange={(v) => updateEditField("loading_date", v)} />
                            <div className="field">
                              <label>Motorista</label>
                              <input value={editForm.driver_name} onChange={(e) => updateEditField("driver_name", formatNome(e.target.value))} />
                            </div>
                            <div className="field">
                              <label>CPF</label>
                              <input value={editForm.driver_cpf} onChange={(e) => updateEditField("driver_cpf", formatCPF(e.target.value))} maxLength={14} />
                            </div>
                            <div className="field">
                              <label>CNH</label>
                              <input value={editForm.cnh} onChange={(e) => updateEditField("cnh", e.target.value)} />
                            </div>
                            <div className="field">
                              <label>Telefone</label>
                              <input value={editForm.driver_phone} onChange={(e) => updateEditField("driver_phone", formatPhone(e.target.value))} />
                            </div>
                            <div className="field">
                              <label>Placa Cavalo</label>
                              <input value={editForm.plate_cavalo} onChange={(e) => updateEditField("plate_cavalo", formatPlaca(e.target.value))} />
                            </div>
                            <div className="field">
                              <label>Placa Carreta 1</label>
                              <input value={editForm.plate_carreta1} onChange={(e) => updateEditField("plate_carreta1", formatPlaca(e.target.value))} />
                            </div>
                            <div className="field">
                              <label>Placa Carreta 2</label>
                              <input value={editForm.plate_carreta2} onChange={(e) => updateEditField("plate_carreta2", formatPlaca(e.target.value))} />
                            </div>
                            <div className="field">
                              <label>Modelo do veículo</label>
                              <select value={editForm.modelo_veiculo} onChange={(e) => updateEditField("modelo_veiculo", e.target.value)}>
                                <option value="">Selecione</option>
                                {MODELOS_VEICULO.map((m) => <option key={m.valor} value={m.valor}>{m.rotulo}</option>)}
                              </select>
                            </div>
                          </div>

                          <table>
                            <thead>
                              <tr>
                                <th>Pedido</th>
                                <th>Produto</th>
                                <th>Embalagem</th>
                                <th>Toneladas</th>
                                <th>Cidade/UF</th>
                                <th>Cliente</th>
                                <th></th>
                              </tr>
                            </thead>
                            <tbody>
                              {editForm.itens.map((it, idx) => (
                                <tr key={idx}>
                                  <td style={{ minWidth: 280 }}>
                                    <select value={it.pedido_id ?? ""} onChange={(e) => selecionarPedidoNaEdicao(idx, e.target.value)}>
                                      <option value="">
                                        {it.contrato ? `${it.contrato} (sem vínculo) — escolha o pedido` : "Selecione um pedido cadastrado"}
                                      </option>
                                      {pedidosEdicao
                                        .filter((p) => p.toneladas_restante > 0.001 || String(p.id) === String(it.pedido_id))
                                        .map((p) => (
                                          <option key={p.id} value={p.id}>
                                            {p.novo ? "NOVO · " : ""}{p.contrato || "s/nº"} · {p.cliente} · {p.produto} · {formatTon(p.toneladas_restante)} t restantes
                                          </option>
                                        ))}
                                    </select>
                                  </td>
                                  <td>{it.produto || "-"}</td>
                                  <td>{it.embalagem || "-"}</td>
                                  <td>
                                    <input
                                      style={{ width: 96 }}
                                      value={it.toneladas}
                                      disabled={!it.pedido_id && !String(it.contrato || "").trim()}
                                      title={disponivelNaEdicao(it) !== null ? `Disponível: ${formatTon(disponivelNaEdicao(it))} t` : ""}
                                      onChange={(e) => {
                                        const maximo = disponivelNaEdicao(it);
                                        if (e.target.value !== "" && maximo !== null && parseNumero(e.target.value) > maximo + 0.0001) return;
                                        updateEditItem(idx, "toneladas", e.target.value);
                                      }}
                                    />
                                  </td>
                                  <td>{it.cidade || "-"}</td>
                                  <td>{it.cliente || "-"}</td>
                                  <td>
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      onClick={() => setEditForm((prev) => ({ ...prev, itens: prev.itens.filter((_, i) => i !== idx) }))}
                                    >
                                      Remover
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => setEditForm((prev) => ({ ...prev, itens: [...prev.itens, { ...OC_ITEM_VAZIO }] }))}
                          >
                            + Item
                          </button>

                          <div className="field">
                            <label>Observações</label>
                            <textarea
                              value={editForm.observacoes}
                              onChange={(e) => updateEditField("observacoes", e.target.value)}
                              rows={3}
                              style={{ resize: "vertical" }}
                            />
                          </div>

                          {editError && <div style={{ color: "var(--danger)" }}>{editError}</div>}

                          <div style={{ display: "flex", gap: 12 }}>
                            <button className="btn-primary" disabled={editSaving} onClick={salvarERegerar}>
                              {editSaving ? "Salvando..." : "Salvar e Regerar Documentos"}
                            </button>
                            <button className="btn-secondary" onClick={fecharEdicao}>Cancelar</button>
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {!loading && agendamentosExibidos.length === 0 && (
              <tr>
                <td colSpan={8} style={{ color: "var(--muted)" }}>
                  {diaSelecionado ? `Nenhum agendamento em ${diaSelecionado}.` : "Nenhum agendamento encontrado."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
