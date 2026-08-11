import { useState } from "react";
import * as api from "../api/client";

const PRODUTO_VAZIO = { contrato: "", produto: "", embalagem: "", toneladas: "", cidade: "", cliente: "" };

export default function OrdemColetaPage() {
  const [template, setTemplate] = useState("AFL");
  const [dataCarregamento, setDataCarregamento] = useState("");
  const [cpf, setCpf] = useState("");
  const [nome, setNome] = useState("");
  const [cnh, setCnh] = useState("");
  const [fone, setFone] = useState("");
  const [placa1, setPlaca1] = useState("");
  const [placa2, setPlaca2] = useState("");
  const [placa3, setPlaca3] = useState("");
  const [produtos, setProdutos] = useState([{ ...PRODUTO_VAZIO }]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  function updateProduto(idx, field, value) {
    setProdutos((prev) => prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p)));
  }

  function addProduto() {
    setProdutos((prev) => [...prev, { ...PRODUTO_VAZIO }]);
  }

  function removeProduto(idx) {
    setProdutos((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleGerar(formato) {
    setStatus("");
    setLoading(true);
    try {
      await api.gerarOrdemColeta({
        template,
        produtos,
        cpf,
        nome,
        cnh,
        fone,
        placa1,
        placa2,
        placa3,
        data_carregamento: dataCarregamento,
        formato,
      });
      setStatus("Documento gerado com sucesso.");
    } catch (err) {
      setStatus(`Erro: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <h2 style={{ margin: 0 }}>Ordem de Coleta</h2>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="field-grid">
          <div className="field">
            <label>Template</label>
            <select value={template} onChange={(e) => setTemplate(e.target.value)}>
              <option value="AFL">AFL</option>
              <option value="HERINGER">Heringer</option>
            </select>
          </div>
          <div className="field">
            <label>Data de Carregamento</label>
            <input placeholder="dd/mm/aaaa" value={dataCarregamento} onChange={(e) => setDataCarregamento(e.target.value)} />
          </div>
          <div className="field">
            <label>CPF do Motorista</label>
            <input value={cpf} onChange={(e) => setCpf(e.target.value)} />
          </div>
          <div className="field">
            <label>Nome do Motorista</label>
            <input value={nome} onChange={(e) => setNome(e.target.value)} />
          </div>
          <div className="field">
            <label>CNH</label>
            <input value={cnh} onChange={(e) => setCnh(e.target.value)} />
          </div>
          <div className="field">
            <label>Telefone</label>
            <input value={fone} onChange={(e) => setFone(e.target.value)} />
          </div>
          <div className="field">
            <label>Placa Cavalo</label>
            <input value={placa1} onChange={(e) => setPlaca1(e.target.value)} />
          </div>
          <div className="field">
            <label>Placa Carreta 1</label>
            <input value={placa2} onChange={(e) => setPlaca2(e.target.value)} />
          </div>
          <div className="field">
            <label>Placa Carreta 2</label>
            <input value={placa3} onChange={(e) => setPlaca3(e.target.value)} />
          </div>
        </div>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong>Produtos / Pedidos</strong>
          <button className="btn-secondary" onClick={addProduto} type="button">
            + Adicionar item
          </button>
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
            {produtos.map((p, idx) => (
              <tr key={idx}>
                <td><input value={p.contrato} onChange={(e) => updateProduto(idx, "contrato", e.target.value)} /></td>
                <td><input value={p.produto} onChange={(e) => updateProduto(idx, "produto", e.target.value)} /></td>
                <td><input value={p.embalagem} onChange={(e) => updateProduto(idx, "embalagem", e.target.value)} /></td>
                <td><input value={p.toneladas} onChange={(e) => updateProduto(idx, "toneladas", e.target.value)} /></td>
                <td><input value={p.cidade} onChange={(e) => updateProduto(idx, "cidade", e.target.value)} /></td>
                <td><input value={p.cliente} onChange={(e) => updateProduto(idx, "cliente", e.target.value)} /></td>
                <td>
                  <button className="btn-secondary" type="button" onClick={() => removeProduto(idx)}>
                    Remover
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <button className="btn-primary" disabled={loading} onClick={() => handleGerar("docx")}>
          Gerar DOCX
        </button>
        <button className="btn-secondary" disabled={loading} onClick={() => handleGerar("pdf")}>
          Gerar PDF
        </button>
        {status && <span style={{ fontSize: 13, color: status.startsWith("Erro") ? "var(--danger)" : "var(--success)" }}>{status}</span>}
      </div>
    </div>
  );
}
