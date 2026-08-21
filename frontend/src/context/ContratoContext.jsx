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

const MOTORISTA_VAZIO = {
  nome: "", cpf: "", cnh: "", fone: "", placa1: "", placa2: "", placa3: "",
  roteiro: "", localizador: "", contatoCliente: "", observacoes: "", agendamentoId: null,
};

export function ContratoProvider({ children }) {
  const [rows, setRows] = useState([]);
  const [dataCarregamento, setDataCarregamento] = useState(todayFormatted);
  const [supplier, setSupplier] = useState("AFL");
  const [motorista, setMotorista] = useState(MOTORISTA_VAZIO);

  function updateMotorista(campo, valor) {
    setMotorista((prev) => ({ ...prev, [campo]: valor }));
  }

  function limparMotorista() {
    setMotorista(MOTORISTA_VAZIO);
  }

  function addRows(newRows) {
    setRows((prev) => [
      ...prev,
      ...newRows.map((r) => ({
        checked: true,
        contrato: r.contrato || "",
        produto: r.produto || "",
        embalagem: r.embalagem || "",
        toneladas: r.toneladas ?? "",
        toneladasOriginal: r.toneladas ?? "",
        cidade: r.cidade || "",
        cliente: r.cliente || "",
        pedidoId: r.pedidoId ?? null,
      })),
    ]);
  }

  function substituirRows(newRows) {
    setRows(
      newRows.map((r) => ({
        checked: true,
        contrato: r.contrato || "",
        produto: r.produto || "",
        embalagem: r.embalagem || "",
        toneladas: r.toneladas ?? "",
        toneladasOriginal: r.toneladas ?? "",
        cidade: r.cidade || "",
        cliente: r.cliente || "",
        pedidoId: r.pedidoId ?? null,
      }))
    );
  }

  function toggleRow(index) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, checked: !r.checked } : r)));
  }

  function updateRowField(index, field, value) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
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
        motorista,
        updateMotorista,
        limparMotorista,
        addRows,
        substituirRows,
        toggleRow,
        updateRowField,
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
