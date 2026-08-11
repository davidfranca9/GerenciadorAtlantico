import { useState } from "react";
import * as api from "../api/client";

function UploadBlock({ title, actionFn, resultRenderer }) {
  const [file, setFile] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleEnviar() {
    if (!file) return;
    setError("");
    setLoading(true);
    setResultado(null);
    try {
      const data = await actionFn(file);
      setResultado(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <strong>{title}</strong>
      <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
      <button className="btn-primary" onClick={handleEnviar} disabled={!file || loading} style={{ alignSelf: "start" }}>
        {loading ? "Processando..." : "Enviar e Extrair"}
      </button>
      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}
      {resultado && (resultRenderer ? resultRenderer(resultado) : (
        <pre style={{ background: "var(--bg)", padding: 12, borderRadius: 6, overflowX: "auto", fontSize: 12 }}>
          {JSON.stringify(resultado, null, 2)}
        </pre>
      ))}
    </div>
  );
}

export default function ContratoPage() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <h2 style={{ margin: 0 }}>Contrato (OCR)</h2>
      <p style={{ color: "var(--text-muted)", marginTop: -10 }}>
        Envie o PDF/imagem do pedido, CNH ou CRLV. O texto e extraido via Azure OCR e os dados relevantes ficam prontos para copiar na Ordem de Coleta.
      </p>

      <UploadBlock title="Pedido Heringer (PDF/imagem)" actionFn={api.ocrPedidoHeringer} />
      <UploadBlock title="Pedido em PDF (texto, layout padrao)" actionFn={api.parsePdfPedido} />
      <UploadBlock title="CNH do motorista" actionFn={api.ocrCnh} />
      <UploadBlock title="CRLV do veiculo" actionFn={api.ocrCrlv} />
    </div>
  );
}
