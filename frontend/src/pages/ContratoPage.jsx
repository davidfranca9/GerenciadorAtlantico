import { useState } from "react";
import * as api from "../api/client";
import { useContrato } from "../context/ContratoContext";

export default function ContratoPage() {
  const {
    rows,
    metrics,
    dataCarregamento,
    setDataCarregamento,
    supplier,
    setSupplier,
    addRows,
    toggleRow,
    removeRow,
    clearRows,
  } = useContrato();

  const [status, setStatus] = useState("Nenhum contrato carregado. Selecione os PDFs.");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleFiles(e) {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setError("");
    setLoading(true);

    let extracted = [];
    let semItens = 0;
    for (const file of files) {
      try {
        const data = await api.parsePdfPedido(file);
        const produtos = data.produtos || [];
        if (produtos.length === 0) {
          semItens += 1;
        } else {
          extracted = extracted.concat(produtos);
        }
      } catch (err) {
        semItens += 1;
      }
    }

    addRows(extracted);
    setLoading(false);
    e.target.value = "";

    if (extracted.length > 0) {
      setStatus(
        semItens > 0
          ? `${extracted.length} produto(s) carregado(s). ${semItens} PDF(s) nao geraram itens.`
          : `${extracted.length} produto(s) carregado(s) de ${files.length} PDF(s).`
      );
    } else {
      setStatus("Nenhum contrato foi extraido dos PDFs selecionados.");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <strong style={{ fontSize: 15 }}>Filtro de Carregamento</strong>
          <label className="btn-primary" style={{ cursor: "pointer" }}>
            {loading ? "Processando..." : "Selecionar Contratos (PDF)"}
            <input type="file" accept=".pdf" multiple onChange={handleFiles} disabled={loading} style={{ display: "none" }} />
          </label>
        </div>
        <div style={{ fontSize: 13, color: "var(--muted)" }}>{status}</div>
        {error && <div style={{ color: "var(--danger)" }}>{error}</div>}

        <div style={{ display: "flex", gap: 28, flexWrap: "wrap", paddingTop: 6, borderTop: "1px solid var(--border-soft)" }}>
          <div className="field" style={{ minWidth: 220 }}>
            <label>Data de Carregamento</label>
            <input placeholder="dd/mm/aaaa" value={dataCarregamento} onChange={(e) => setDataCarregamento(e.target.value)} />
          </div>
          <div className="field">
            <label>Fornecedor</label>
            <div style={{ display: "flex", gap: 10, height: 40, alignItems: "center" }}>
              {[["AFL", "Fertimax"], ["HERINGER", "Heringer"]].map(([value, texto]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setSupplier(value)}
                  className={supplier === value ? "btn-primary" : "btn-secondary"}
                  style={{ padding: "8px 20px" }}
                >
                  {texto}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 20px" }}>
          <strong style={{ fontSize: 15 }}>Contratos Disponiveis</strong>
          {rows.length > 0 && (
            <button className="btn-secondary" onClick={clearRows}>Limpar tabela</button>
          )}
        </div>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th></th>
                <th>Produto</th>
                <th>Toneladas</th>
                <th>Embalagem</th>
                <th>Pedido</th>
                <th>Cliente</th>
                <th>Cidade</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx} style={{ opacity: row.checked ? 1 : 0.45 }}>
                  <td><input type="checkbox" checked={row.checked} onChange={() => toggleRow(idx)} /></td>
                  <td>{row.produto}</td>
                  <td>{row.toneladas}</td>
                  <td>{row.embalagem}</td>
                  <td>{row.contrato}</td>
                  <td>{row.cliente}</td>
                  <td>{row.cidade}</td>
                  <td><button className="btn-secondary" onClick={() => removeRow(idx)}>Remover</button></td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={8} style={{ color: "var(--muted)" }}>Nenhum contrato na lista. Selecione PDFs acima.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ display: "flex", gap: 0 }}>
        {[
          ["Toneladas Selecionadas", metrics.totalTons.toFixed(1)],
          ["Produtos Selecionados", metrics.selectedCount],
          ["Produtos na Lista", metrics.totalCount],
          ["Clientes Unicos", metrics.uniqueClients],
        ].map(([label, value], idx, arr) => (
          <div
            key={label}
            style={{
              flex: 1,
              padding: "0 18px",
              borderRight: idx < arr.length - 1 ? "1px solid var(--border-soft)" : "none",
            }}
          >
            <div style={{ fontSize: 20, fontWeight: 700, color: idx === 0 ? "var(--accent-glow)" : "var(--text)" }}>{value}</div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.4 }}>{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
