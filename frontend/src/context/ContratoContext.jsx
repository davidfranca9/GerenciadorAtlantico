import { createContext, useContext, useMemo, useState } from "react";

const ContratoContext = createContext(null);

function safeTon(value) {
  const num = parseFloat(String(value ?? "").replace(",", "."));
  return Number.isFinite(num) ? num : 0;
}

function todayFormatted() {
  const hoje = new Date();
  const dd = String(hoje.getDate()).padStart(2, "0");
  const mm = String(hoje.getMonth() + 1).padStart(2, "0");
  const yyyy = hoje.getFullYear();
  return `${dd}/${mm}/${yyyy}`;
}

export function ContratoProvider({ children }) {
  const [rows, setRows] = useState([]);
  const [dataCarregamento, setDataCarregamento] = useState(todayFormatted);
  const [supplier, setSupplier] = useState("AFL");

  function addRows(newRows) {
    setRows((prev) => [
      ...prev,
      ...newRows.map((r) => ({
        checked: true,
        contrato: r.contrato || "",
        produto: r.produto || "",
        embalagem: r.embalagem || "",
        toneladas: r.toneladas ?? "",
        cidade: r.cidade || "",
        cliente: r.cliente || "",
      })),
    ]);
  }

  function toggleRow(index) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, checked: !r.checked } : r)));
  }

  function removeRow(index) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  function clearRows() {
    setRows([]);
  }

  const selectedRows = useMemo(() => rows.filter((r) => r.checked), [rows]);

  const metrics = useMemo(
    () => ({
      totalTons: selectedRows.reduce((sum, r) => sum + safeTon(r.toneladas), 0),
      selectedCount: selectedRows.length,
      totalCount: rows.length,
      uniqueClients: new Set(selectedRows.map((r) => r.cliente).filter(Boolean)).size,
    }),
    [rows, selectedRows]
  );

  return (
    <ContratoContext.Provider
      value={{
        rows,
        selectedRows,
        metrics,
        dataCarregamento,
        setDataCarregamento,
        supplier,
        setSupplier,
        addRows,
        toggleRow,
        removeRow,
        clearRows,
      }}
    >
      {children}
    </ContratoContext.Provider>
  );
}

export function useContrato() {
  return useContext(ContratoContext);
}
