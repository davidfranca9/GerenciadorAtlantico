import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api/client";
import Icon from "../components/Icon";
import { useContrato } from "../context/ContratoContext";

const SUPPLIER_LABEL = { AFL: "Fertimax", HERINGER: "Heringer" };

function parseNumero(texto) {
  const num = parseFloat(String(texto ?? "").replace(",", "."));
  return Number.isFinite(num) ? num : 0;
}

function formatTon(valor) {
  return parseNumero(valor).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

export default function PedidosPage() {
  const navigate = useNavigate();
  const { substituirRows, setSupplier } = useContrato();

  const [pedidos, setPedidos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busca, setBusca] = useState("");

  const [importSupplier, setImportSupplier] = useState("AFL");
  const [importando, setImportando] = useState(false);
  const [status, setStatus] = useState("");

  const [selecionados, setSelecionados] = useState({}); // { [pedidoId]: quantidade }

  async function carregar() {
    setLoading(true);
    setError("");
    try {
      setPedidos(await api.listarPedidos());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    carregar();
  }, []);

  async function handleImportar(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    setImportando(true);
    setError("");
    let total = 0;
    for (const file of files) {
      try {
        const resultado = await api.importarPedidoPdf(file, importSupplier);
        total += resultado.pedidos?.length || 0;
      } catch (err) {
        setError(`Erro ao importar ${file.name}: ${err.message}`);
      }
    }
    setStatus(total > 0 ? `${total} pedido(s) importado(s) com sucesso.` : "Nenhum pedido foi extraído dos PDFs.");
    setImportando(false);
    await carregar();
  }

  async function handleExcluir(pedido) {
    if (!window.confirm(`Excluir o pedido "${pedido.contrato || pedido.produto}"? Essa ação não pode ser desfeita.`)) return;
    try {
      await api.excluirPedido(pedido.id);
      setPedidos((prev) => prev.filter((p) => p.id !== pedido.id));
      setSelecionados((prev) => {
        const { [pedido.id]: _removido, ...resto } = prev;
        return resto;
      });
    } catch (err) {
      setError(err.message);
    }
  }

  function toggleSelecionado(pedido) {
    setSelecionados((prev) => {
      if (prev[pedido.id] !== undefined) {
        const { [pedido.id]: _removido, ...resto } = prev;
        return resto;
      }
      return { ...prev, [pedido.id]: pedido.toneladas_restante };
    });
  }

  function updateQuantidade(pedido, texto) {
    const max = pedido.toneladas_restante;
    const valor = parseNumero(texto);
    const limitado = texto === "" ? "" : Math.min(valor, max);
    setSelecionados((prev) => ({ ...prev, [pedido.id]: limitado }));
  }

  const pedidosFiltrados = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    if (!termo) return pedidos;
    return pedidos.filter((p) =>
      [p.contrato, p.produto, p.cliente, p.cidade].some((campo) => (campo || "").toLowerCase().includes(termo))
    );
  }, [pedidos, busca]);

  const selecionadosLista = Object.entries(selecionados).filter(([, qtd]) => parseNumero(qtd) > 0);
  const totalSelecionado = selecionadosLista.reduce((soma, [, qtd]) => soma + parseNumero(qtd), 0);

  function handleEnviarParaOc() {
    const linhas = selecionadosLista
      .map(([id, qtd]) => {
        const pedido = pedidos.find((p) => String(p.id) === id);
        if (!pedido) return null;
        return {
          contrato: pedido.contrato,
          produto: pedido.produto,
          embalagem: pedido.embalagem,
          toneladas: String(qtd),
          cidade: pedido.cidade,
          cliente: pedido.cliente,
          pedidoId: pedido.id,
        };
      })
      .filter(Boolean);
    if (!linhas.length) return;

    const suppliers = new Set(selecionadosLista.map(([id]) => pedidos.find((p) => String(p.id) === id)?.supplier));
    setSupplier(suppliers.size === 1 ? [...suppliers][0] : "AFL");
    substituirRows(linhas);
    navigate("/ordem-coleta");
  }

  return (
    <div className="ops-page pedidos-page">
      <div className="pedidos-toolbar">
        <div className="field" style={{ maxWidth: 320 }}>
          <label>Buscar pedido</label>
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Pedido, produto, cliente ou cidade" />
        </div>
        <div className="pedidos-import">
          <div className="pedidos-supplier-toggle">
            {[["AFL", "Fertimax"], ["HERINGER", "Heringer"]].map(([value, texto]) => (
              <button key={value} type="button" className={importSupplier === value ? "btn-primary" : "btn-secondary"} onClick={() => setImportSupplier(value)}>
                {texto}
              </button>
            ))}
          </div>
          <label className="btn-primary" style={{ cursor: "pointer" }}>
            {importando ? "Importando..." : <><Icon name="upload" size={16} />Importar Pedidos (PDF)</>}
            <input type="file" accept=".pdf" multiple onChange={handleImportar} disabled={importando} style={{ display: "none" }} />
          </label>
        </div>
      </div>

      {status && <div className="inline-alert info"><span className="status-dot" />{status}</div>}
      {error && <div className="inline-alert error">{error}</div>}

      {loading ? (
        <div className="inline-alert info"><span className="status-dot" />Carregando pedidos...</div>
      ) : pedidosFiltrados.length === 0 ? (
        <div className="inline-alert warning">Nenhum pedido encontrado. Importe PDFs para começar.</div>
      ) : (
        <div className="pedidos-grid">
          {pedidosFiltrados.map((p) => {
            const percentual = p.toneladas_total > 0 ? Math.min(100, (p.toneladas_usadas / p.toneladas_total) * 100) : 0;
            const selecionado = selecionados[p.id] !== undefined;
            const esgotando = p.toneladas_restante <= p.toneladas_total * 0.1;
            return (
              <div key={p.id} className={`pedido-card ${selecionado ? "selected" : ""}`}>
                <div className="pedido-card-top">
                  <span className="pedido-badge">{SUPPLIER_LABEL[p.supplier] || p.supplier}</span>
                  <button className="icon-btn" title="Excluir pedido" onClick={() => handleExcluir(p)}><Icon name="trash" size={14} /></button>
                </div>
                <strong className="pedido-produto">{p.produto || "Produto"}</strong>
                <div className="pedido-meta">
                  <span><Icon name="contract" size={13} />{p.contrato || "Sem número"}</span>
                  <span><Icon name="truck" size={13} />{p.embalagem || "-"}</span>
                </div>
                <div className="pedido-meta">
                  <span>{p.cliente || "Cliente não identificado"}</span>
                  <span>{p.cidade || "-"}</span>
                </div>

                <div className="pedido-progress">
                  <div className="pedido-progress-bar"><div className="pedido-progress-fill" style={{ width: `${percentual}%` }} /></div>
                  <div className="pedido-progress-labels">
                    <span>{formatTon(p.toneladas_usadas)} / {formatTon(p.toneladas_total)} t usadas</span>
                    <span className={`pedido-restante ${esgotando ? "low" : ""}`}>{formatTon(p.toneladas_restante)} t restantes</span>
                  </div>
                </div>

                <div className="pedido-select-row">
                  <label className="pedido-select">
                    <input type="checkbox" checked={selecionado} onChange={() => toggleSelecionado(p)} />
                    <span>Selecionar</span>
                  </label>
                  {selecionado && (
                    <input
                      className="pedido-qtd-input"
                      value={selecionados[p.id]}
                      onChange={(e) => updateQuantidade(p, e.target.value)}
                      title={`Máximo: ${formatTon(p.toneladas_restante)}`}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selecionadosLista.length > 0 && (
        <div className="action-dock">
          <div>
            <span>SELECIONADOS</span>
            <strong>{selecionadosLista.length} pedido(s) · {formatTon(totalSelecionado)} toneladas</strong>
          </div>
          <div className="action-buttons">
            <button className="btn-primary" onClick={handleEnviarParaOc}>
              <Icon name="file" size={16} />Enviar para Ordem de Coleta
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
