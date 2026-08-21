import { Fragment, useEffect, useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";
import { formatCPF, formatNome, formatPhone, formatPlaca } from "../utils/format";

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

export default function AgendamentosPage() {
  const [agendamentos, setAgendamentos] = useState([]);
  const [filtroStatus, setFiltroStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [supplier, setSupplier] = useState("");
  const [loadingDate, setLoadingDate] = useState("");
  const [driverName, setDriverName] = useState("");
  const [plateCavalo, setPlateCavalo] = useState("");
  const [itens, setItens] = useState([{ ...ITEM_VAZIO }]);
  const [error, setError] = useState("");
  const [pedidosDisponiveis, setPedidosDisponiveis] = useState([]);

  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");

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
      const full = await api.obterAgendamento(a.id);
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
        observacoes: full.observacoes || "",
        itens: full.itens.length
          ? full.itens.map((it) => ({
              contrato: it.pedido || "",
              cliente: it.cliente || "",
              produto: it.produto || "",
              cidade: it.cidade || "",
              embalagem: it.embalagem || "",
              toneladas: String(it.toneladas ?? ""),
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

  function updateEditItem(idx, field, value) {
    setEditForm((prev) => ({
      ...prev,
      itens: prev.itens.map((it, i) => (i === idx ? { ...it, [field]: value } : it)),
    }));
  }

  async function salvarERegerar() {
    setEditSaving(true);
    setEditError("");
    try {
      const payload = {
        template: editForm.template,
        produtos: editForm.itens,
        cpf: editForm.driver_cpf,
        nome: editForm.driver_name,
        cnh: editForm.cnh,
        fone: editForm.driver_phone,
        placa1: editForm.plate_cavalo,
        placa2: editForm.plate_carreta1,
        placa3: editForm.plate_carreta2,
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancelar" : "+ Novo Agendamento"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCriar} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="field-grid">
            <div className="field">
              <label>Fornecedor</label>
              <input value={supplier} onChange={(e) => setSupplier(e.target.value)} required />
            </div>
            <DateField label="Data de Carregamento" value={loadingDate} onChange={setLoadingDate} />
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
                          {p.contrato || "s/nº"} · {p.produto} · {formatTon(p.toneladas_restante)}t restantes
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

      <div className="field" style={{ maxWidth: 260 }}>
        <label>Filtrar por status</label>
        <select value={filtroStatus} onChange={(e) => setFiltroStatus(e.target.value)}>
          <option value="">Todos</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Fornecedor</th>
              <th>Data</th>
              <th>Motorista</th>
              <th>Itens</th>
              <th>Toneladas</th>
              <th>Observações</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {agendamentos.map((a) => (
              <Fragment key={a.id}>
                <tr>
                  <td>{a.supplier}</td>
                  <td>{a.loading_date}</td>
                  <td>{a.driver_name}</td>
                  <td>{a.total_items}</td>
                  <td>{a.total_tons}</td>
                  <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.observacoes}>
                    {a.observacoes || "-"}
                  </td>
                  <td>
                    <select value={a.status} onChange={(e) => handleStatus(a.id, e.target.value)}>
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td style={{ display: "flex", gap: 8 }}>
                    <button className="btn-secondary" onClick={() => (editId === a.id ? fecharEdicao() : abrirEdicao(a))}>
                      {editId === a.id ? "Fechar" : "Editar"}
                    </button>
                    <button className="btn-ghost" onClick={() => handleExcluir(a)}>Excluir</button>
                  </td>
                </tr>
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
                                  <td><input value={it.contrato} onChange={(e) => updateEditItem(idx, "contrato", e.target.value)} /></td>
                                  <td><input value={it.produto} onChange={(e) => updateEditItem(idx, "produto", e.target.value)} /></td>
                                  <td><input value={it.embalagem} onChange={(e) => updateEditItem(idx, "embalagem", e.target.value)} /></td>
                                  <td><input value={it.toneladas} onChange={(e) => updateEditItem(idx, "toneladas", e.target.value)} /></td>
                                  <td><input value={it.cidade} onChange={(e) => updateEditItem(idx, "cidade", e.target.value)} /></td>
                                  <td><input value={it.cliente} onChange={(e) => updateEditItem(idx, "cliente", e.target.value)} /></td>
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
            {!loading && agendamentos.length === 0 && (
              <tr>
                <td colSpan={8} style={{ color: "var(--muted)" }}>Nenhum agendamento encontrado.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
