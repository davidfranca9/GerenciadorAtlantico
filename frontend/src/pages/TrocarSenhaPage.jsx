import { useState } from "react";
import * as api from "../api/client";

export default function TrocarSenhaPage() {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setStatus("");
    if (nova !== confirmar) {
      setError("A confirmacao nao coincide com a nova senha.");
      return;
    }
    try {
      await api.changePassword(atual, nova);
      setStatus("Senha alterada com sucesso.");
      setAtual("");
      setNova("");
      setConfirmar("");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ maxWidth: 360 }}>
      <h2 style={{ marginTop: 0 }}>Trocar Senha</h2>
      <form onSubmit={handleSubmit} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="field">
          <label>Senha atual</label>
          <input type="password" value={atual} onChange={(e) => setAtual(e.target.value)} required />
        </div>
        <div className="field">
          <label>Nova senha</label>
          <input type="password" value={nova} onChange={(e) => setNova(e.target.value)} required minLength={8} />
        </div>
        <div className="field">
          <label>Confirmar nova senha</label>
          <input type="password" value={confirmar} onChange={(e) => setConfirmar(e.target.value)} required minLength={8} />
        </div>
        {error && <div style={{ color: "var(--danger)" }}>{error}</div>}
        {status && <div style={{ color: "var(--success)" }}>{status}</div>}
        <button type="submit" className="btn-primary">Salvar nova senha</button>
      </form>
    </div>
  );
}
