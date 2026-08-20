import { useEffect, useState } from "react";
import * as api from "../api/client";
import { formatNome, formatPlaca } from "../utils/format";

export default function BuonnyPage() {
  const [lookups, setLookups] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [resultado, setResultado] = useState(null);

  const [form, setForm] = useState({
    codigo: "", cpf: "", nome: "", placa_veiculo: "", placa_carreta: "",
    carga_tipo: "", carga_valor: "", origem_cidade: "", origem_estado: "",
    destino_cidade: "", destino_estado: "",
  });

  useEffect(() => {
    api.buonnyLookups().then(setLookups).catch(() => {});
  }, []);

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const data = await api.buonnyLogin(username, password);
      setSessionId(data.session_id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleConsultar(e) {
    e.preventDefault();
    setError("");
    setResultado(null);
    try {
      const data = await api.buonnyConsultar({ session_id: sessionId, ...form });
      setResultado(data);
    } catch (err) {
      setError(err.message);
    }
  }

  if (!sessionId) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 360 }}>
        <form onSubmit={handleLogin} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="field">
            <label>Apelido (Codigo)</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div className="field">
            <label>Senha</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <div style={{ color: "var(--danger)" }}>{error}</div>}
          <button type="submit" className="btn-primary">Entrar na Buonny</button>
        </form>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <form onSubmit={handleConsultar} className="card field-grid">
        <div className="field"><label>Codigo Cliente</label><input value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} /></div>
        <div className="field"><label>CPF Motorista</label><input value={form.cpf} onChange={(e) => setForm({ ...form, cpf: e.target.value })} /></div>
        <div className="field"><label>Nome Motorista</label><input value={form.nome} onChange={(e) => setForm({ ...form, nome: formatNome(e.target.value) })} /></div>
        <div className="field"><label>Placa veículo</label><input value={form.placa_veiculo} onChange={(e) => setForm({ ...form, placa_veiculo: formatPlaca(e.target.value) })} placeholder="ABC-1D23" /></div>
        <div className="field"><label>Placa Carreta</label><input value={form.placa_carreta} onChange={(e) => setForm({ ...form, placa_carreta: formatPlaca(e.target.value) })} placeholder="ABC-1D23" /></div>
        <div className="field">
          <label>Tipo de Carga</label>
          <select value={form.carga_tipo} onChange={(e) => setForm({ ...form, carga_tipo: e.target.value })}>
            <option value="">Selecione</option>
            {lookups && Object.keys(lookups.carga_tipo).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Valor da Carga</label>
          <select value={form.carga_valor} onChange={(e) => setForm({ ...form, carga_valor: e.target.value })}>
            <option value="">Selecione</option>
            {lookups && Object.keys(lookups.carga_valor).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div className="field"><label>Cidade Origem</label><input value={form.origem_cidade} onChange={(e) => setForm({ ...form, origem_cidade: e.target.value })} /></div>
        <div className="field"><label>UF Origem</label><input value={form.origem_estado} maxLength={2} onChange={(e) => setForm({ ...form, origem_estado: e.target.value.toUpperCase() })} /></div>
        <div className="field"><label>Cidade Destino</label><input value={form.destino_cidade} onChange={(e) => setForm({ ...form, destino_cidade: e.target.value })} /></div>
        <div className="field"><label>UF Destino</label><input value={form.destino_estado} maxLength={2} onChange={(e) => setForm({ ...form, destino_estado: e.target.value.toUpperCase() })} /></div>
      </form>
      <button className="btn-primary" onClick={handleConsultar} style={{ alignSelf: "start" }}>Consultar</button>
      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}
      {resultado && (
        <pre className="card" style={{ overflowX: "auto", fontSize: 12 }}>{JSON.stringify(resultado, null, 2)}</pre>
      )}
    </div>
  );
}
