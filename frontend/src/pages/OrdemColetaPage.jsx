import { useState } from "react";
import * as api from "../api/client";
import { useContrato } from "../context/ContratoContext";
import { formatCPF, formatNome, formatPhone, formatPlaca } from "../utils/format";

const SUPPLIER_LABEL = { AFL: "Fertimax", HERINGER: "Heringer" };

function cleanOcrValue(value) {
  const text = String(value || "").trim();
  const lowered = text.toLowerCase();
  if (["nao encontrado", "não encontrado", "nao encontrada", "não encontrada"].includes(lowered)) return "";
  return text;
}

export default function OrdemColetaPage() {
  const { selectedRows, metrics, dataCarregamento, supplier } = useContrato();

  const [nome, setNome] = useState("");
  const [cpf, setCpf] = useState("");
  const [cnh, setCnh] = useState("");
  const [fone, setFone] = useState("");
  const [placa1, setPlaca1] = useState("");
  const [placa2, setPlaca2] = useState("");
  const [placa3, setPlaca3] = useState("");
  const [roteiro, setRoteiro] = useState("");
  const [localizador, setLocalizador] = useState("");
  const [contatoCliente, setContatoCliente] = useState("");
  const [observacoes, setObservacoes] = useState("");
  const [agendamentoId, setAgendamentoId] = useState(null);

  const [status, setStatus] = useState("Importe os documentos e revise os dados antes de gerar a O.C.");
  const [error, setError] = useState("");
  const [loadingAction, setLoadingAction] = useState("");

  function buildPayload() {
    return {
      template: supplier,
      produtos: selectedRows.map((r) => ({
        contrato: r.contrato,
        produto: r.produto,
        embalagem: r.embalagem,
        toneladas: String(r.toneladas),
        cidade: r.cidade,
        cliente: r.cliente,
      })),
      cpf,
      nome,
      cnh,
      fone,
      placa1,
      placa2,
      placa3,
      data_carregamento: dataCarregamento,
      observacoes,
      agendamento_id: agendamentoId,
    };
  }

  async function handleImportCnh(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    try {
      const data = await api.ocrCnh(file);
      setNome(formatNome(cleanOcrValue(data.nome)));
      setCpf(formatCPF(cleanOcrValue(data.cpf)));
      setCnh(cleanOcrValue(data.numero));
      setStatus(`CNH importada com sucesso de ${file.name}.`);
    } catch (err) {
      setError(`Erro ao ler CNH: ${err.message}`);
    }
  }

  async function handleImportCrlv(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    try {
      const data = await api.ocrCrlv(file);
      const placa = cleanOcrValue(data.placa);
      const categoria = cleanOcrValue(data.categoria_veiculo).toUpperCase();
      if (!placa) {
        setError("Nenhuma placa foi encontrada no CRLV.");
        return;
      }
      const placaFormatada = formatPlaca(placa);
      if (categoria === "CAVALO" || categoria === "TRUCK") {
        setPlaca1(placaFormatada);
        setStatus("CRLV importado com sucesso para o campo Placa Cavalo.");
      } else if (!placa2) {
        setPlaca2(placaFormatada);
        setStatus("CRLV importado com sucesso para o campo Placa Carreta 1.");
      } else {
        setPlaca3(placaFormatada);
        setStatus("CRLV importado com sucesso para o campo Placa Carreta 2.");
      }
    } catch (err) {
      setError(`Erro ao ler CRLV: ${err.message}`);
    }
  }

  async function handleGerar() {
    setError("");
    if (selectedRows.length === 0) {
      setError("Selecione os contratos na aba Contrato antes de gerar a O.C.");
      return;
    }
    if (!nome.trim()) {
      setError("O nome do motorista e obrigatorio.");
      return;
    }
    setLoadingAction("pdf");
    try {
      const payload = buildPayload();
      const result = await api.gerarOrdemColeta(payload);
      if (result?.agendamentoId) setAgendamentoId(result.agendamentoId);
      if (supplier !== "HERINGER") {
        await api.gerarAutorizacaoColeta({ ...payload, agendamento_id: result?.agendamentoId ?? agendamentoId });
        setStatus("O.C. e autorização de coleta geradas com sucesso.");
      } else {
        setStatus("O.C. gerada com sucesso.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingAction("");
    }
  }

  async function handleEnviarEmail() {
    setError("");
    if (selectedRows.length === 0) {
      setError("Selecione os contratos na aba Contrato antes de enviar a O.C.");
      return;
    }
    if (!nome.trim()) {
      setError("O nome do motorista e obrigatorio.");
      return;
    }
    setLoadingAction("email");
    try {
      const payload = { ...buildPayload(), roteiro, localizador, contato_cliente: contatoCliente };
      const result = await api.enviarOrdemColetaEmail(payload);
      if (result?.agendamento_id) setAgendamentoId(result.agendamento_id);
      setStatus(`E-mail enviado e agendamento #${result.agendamento_id} registrado com sucesso.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingAction("");
    }
  }

  function handleLimpar() {
    setNome(""); setCpf(""); setCnh(""); setFone("");
    setPlaca1(""); setPlaca2(""); setPlaca3("");
    setRoteiro(""); setLocalizador(""); setContatoCliente("");
    setObservacoes(""); setAgendamentoId(null);
    setStatus("Campos limpos. Importe novamente CNH e CRLV se necessario.");
    setError("");
  }

  const preview = selectedRows.slice(0, 3).map((r) => {
    const cidade = r.cidade ? ` | ${r.cidade}` : "";
    return `Pedido ${r.contrato || "-"} - ${r.produto || "Produto sem nome"} - ${r.toneladas || 0} t${cidade}`;
  });
  if (selectedRows.length > 3) preview.push(`... e mais ${selectedRows.length - 3} item(ns)`);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <strong style={{ fontSize: 15 }}>Dados do motorista e veículo</strong>

        <div className="card" style={{ display: "flex", padding: 0, background: "transparent", border: "1px solid var(--border-soft)", boxShadow: "none" }}>
          {[
            ["Fornecedor", SUPPLIER_LABEL[supplier] || supplier],
            ["Data", dataCarregamento || "-"],
            ["Pedidos", new Set(selectedRows.map((r) => r.contrato).filter(Boolean)).size],
            ["Produtos", metrics.selectedCount],
          ].map(([label, value], idx, arr) => (
            <div key={label} style={{ flex: 1, padding: "12px 16px", borderRight: idx < arr.length - 1 ? "1px solid var(--border-soft)" : "none" }}>
              <div style={{ fontSize: 10.5, color: "var(--muted)", textTransform: "uppercase" }}>{label}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: idx >= 2 ? "var(--accent-glow)" : "var(--text)" }}>{value}</div>
            </div>
          ))}
        </div>

        {selectedRows.length > 0 ? (
          <div style={{ fontSize: 12.5, color: "var(--muted)" }}>{preview.join(" | ")}</div>
        ) : (
          <div style={{ fontSize: 12.5, color: "var(--warning)" }}>Nenhum contrato selecionado na aba Contrato.</div>
        )}

        <div className="field-grid">
          <div className="field"><label>Nome do Motorista</label><input value={nome} onChange={(e) => setNome(formatNome(e.target.value))} placeholder="Nome completo" /></div>
          <div className="field"><label>CPF</label><input value={cpf} onChange={(e) => setCpf(formatCPF(e.target.value))} placeholder="000.000.000-00" maxLength={14} /></div>
          <div className="field"><label>CNH</label><input value={cnh} onChange={(e) => setCnh(e.target.value)} placeholder="Número da CNH" /></div>
          <div className="field"><label>Telefone</label><input value={fone} onChange={(e) => setFone(formatPhone(e.target.value))} placeholder="(00) 9 0000-0000" /></div>
          <div className="field"><label>Placa Cavalo</label><input value={placa1} onChange={(e) => setPlaca1(formatPlaca(e.target.value))} placeholder="ABC-1D23" /></div>
          <div className="field"><label>Placa Carreta 1</label><input value={placa2} onChange={(e) => setPlaca2(formatPlaca(e.target.value))} placeholder="ABC-1D23" /></div>
          <div className="field"><label>Placa Carreta 2</label><input value={placa3} onChange={(e) => setPlaca3(formatPlaca(e.target.value))} placeholder="ABC-1D23" /></div>
        </div>

        {status && <div style={{ fontSize: 12.5, color: "var(--muted)" }}>{status}</div>}
        {error && <div style={{ fontSize: 12.5, color: "var(--danger)" }}>{error}</div>}

        <div style={{ display: "flex", gap: 12 }}>
          <label className="btn-secondary" style={{ cursor: "pointer" }}>
            Importar Dados da CNH
            <input type="file" accept=".pdf,.jpg,.jpeg,.png,.bmp" onChange={handleImportCnh} style={{ display: "none" }} />
          </label>
          <label className="btn-secondary" style={{ cursor: "pointer" }}>
            Importar Dados do CRLV
            <input type="file" accept=".pdf,.jpg,.jpeg,.png,.bmp" onChange={handleImportCrlv} style={{ display: "none" }} />
          </label>
        </div>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <strong style={{ fontSize: 15 }}>Roteiro / Contato do Cliente (opcional)</strong>
        <div className="field-grid">
          <div className="field"><label>Localizador</label><input value={localizador} onChange={(e) => setLocalizador(e.target.value)} /></div>
          <div className="field"><label>Contato do Cliente</label><input value={contatoCliente} onChange={(e) => setContatoCliente(e.target.value)} /></div>
        </div>
        <div className="field"><label>Roteiro</label><input value={roteiro} onChange={(e) => setRoteiro(e.target.value)} placeholder="Detalhes do roteiro de entrega" /></div>
        <div className="field">
          <label>Observações</label>
          <textarea
            value={observacoes}
            onChange={(e) => setObservacoes(e.target.value)}
            placeholder="Observações que aparecem na O.C."
            rows={3}
            style={{ resize: "vertical", fontFamily: "inherit", fontSize: "inherit" }}
          />
        </div>
      </div>

      <div className="card" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button className="btn-primary" disabled={!!loadingAction} onClick={handleGerar}>
          {loadingAction === "pdf" ? "Gerando..." : "Gerar O.C. (PDF)"}
        </button>
        <button className="btn-secondary" disabled={!!loadingAction} onClick={handleEnviarEmail}>
          {loadingAction === "email" ? "Enviando..." : "Enviar O.C. por E-mail"}
        </button>
        <button className="btn-secondary" disabled={!!loadingAction} onClick={handleLimpar}>
          Limpar os Campos
        </button>
      </div>
    </div>
  );
}
