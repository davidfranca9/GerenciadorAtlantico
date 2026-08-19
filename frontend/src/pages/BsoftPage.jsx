import { useEffect, useState } from "react";
import * as api from "../api/client";
import { formatNome, formatPhone, formatPlaca } from "../utils/format";

export default function BsoftPage() {
  const [lookups, setLookups] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [pf, setPf] = useState({ nome: "", cpf: "", dtNascimento: "", rntrc: "", fone: "", is_owner: false });
  const [veiculo, setVeiculo] = useState({
    placa: "", renavam: "", rntrc: "", tara: "", capacidadeCarga: "", modeloVeiculo: "",
    quantidadeEixos: "", categoriaVeiculo: "", grupoVeiculo: "", tipoRodado: "", tipoCarroceria: "",
    estado: "", cidade: "", motoristaEhProprietario: false,
  });

  useEffect(() => {
    api.bsoftLookups().then(setLookups).catch((err) => setError(err.message));
  }, []);

  async function handleCadastrarPF(e) {
    e.preventDefault();
    setError("");
    setStatus("");
    try {
      await api.bsoftCadastrarPessoaFisica(pf);
      setStatus("Motorista cadastrado na Bsoft com sucesso.");
      setPf({ nome: "", cpf: "", dtNascimento: "", rntrc: "", fone: "", is_owner: false });
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleCadastrarVeiculo(e) {
    e.preventDefault();
    setError("");
    setStatus("");
    try {
      await api.bsoftCadastrarVeiculo({
        ...veiculo,
        tara: veiculo.tara ? Number(veiculo.tara) : null,
        capacidadeCarga: veiculo.capacidadeCarga ? Number(veiculo.capacidadeCarga) : null,
        quantidadeEixos: veiculo.quantidadeEixos ? Number(veiculo.quantidadeEixos) : null,
        categoriaVeiculo: veiculo.categoriaVeiculo ? Number(veiculo.categoriaVeiculo) : null,
        grupoVeiculo: veiculo.grupoVeiculo ? Number(veiculo.grupoVeiculo) : null,
      });
      setStatus("Veiculo cadastrado na Bsoft com sucesso.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {error && <div style={{ color: "var(--danger)" }}>{error}</div>}
      {status && <div style={{ color: "var(--success)" }}>{status}</div>}

      <form onSubmit={handleCadastrarPF} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <strong>Cadastrar Motorista (Pessoa Fisica)</strong>
        <div className="field-grid">
          <div className="field"><label>Nome</label><input value={pf.nome} onChange={(e) => setPf({ ...pf, nome: formatNome(e.target.value) })} required /></div>
          <div className="field"><label>CPF</label><input value={pf.cpf} onChange={(e) => setPf({ ...pf, cpf: e.target.value })} required /></div>
          <div className="field"><label>Data Nascimento</label><input placeholder="aaaa-mm-dd" value={pf.dtNascimento} onChange={(e) => setPf({ ...pf, dtNascimento: e.target.value })} /></div>
          <div className="field"><label>RNTRC</label><input value={pf.rntrc} onChange={(e) => setPf({ ...pf, rntrc: e.target.value })} /></div>
          <div className="field"><label>Telefone</label><input value={pf.fone} onChange={(e) => setPf({ ...pf, fone: formatPhone(e.target.value) })} placeholder="(00) 9 0000-0000" /></div>
        </div>
        <label style={{ fontSize: 13, display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={pf.is_owner} onChange={(e) => setPf({ ...pf, is_owner: e.target.checked })} />
          Tambem e proprietario do veiculo
        </label>
        <button type="submit" className="btn-primary" style={{ alignSelf: "start" }}>Cadastrar na Bsoft</button>
      </form>

      <form onSubmit={handleCadastrarVeiculo} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <strong>Cadastrar Veiculo</strong>
        <div className="field-grid">
          <div className="field"><label>Placa</label><input value={veiculo.placa} onChange={(e) => setVeiculo({ ...veiculo, placa: formatPlaca(e.target.value) })} placeholder="ABC-1D23" required /></div>
          <div className="field"><label>Renavam</label><input value={veiculo.renavam} onChange={(e) => setVeiculo({ ...veiculo, renavam: e.target.value })} /></div>
          <div className="field"><label>Modelo</label><input value={veiculo.modeloVeiculo} onChange={(e) => setVeiculo({ ...veiculo, modeloVeiculo: e.target.value })} /></div>
          <div className="field"><label>Eixos</label><input value={veiculo.quantidadeEixos} onChange={(e) => setVeiculo({ ...veiculo, quantidadeEixos: e.target.value })} /></div>
          <div className="field">
            <label>Categoria</label>
            <select value={veiculo.categoriaVeiculo} onChange={(e) => setVeiculo({ ...veiculo, categoriaVeiculo: e.target.value })}>
              <option value="">Selecione</option>
              {lookups && Object.entries(lookups.categorias_veiculo).map(([nome, id]) => (
                <option key={id} value={id}>{nome}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Grupo</label>
            <select value={veiculo.grupoVeiculo} onChange={(e) => setVeiculo({ ...veiculo, grupoVeiculo: e.target.value })}>
              <option value="">Selecione</option>
              {lookups && Object.entries(lookups.grupos_veiculo).map(([nome, id]) => (
                <option key={id} value={id}>{nome}</option>
              ))}
            </select>
          </div>
          <div className="field"><label>Estado</label><input value={veiculo.estado} maxLength={2} onChange={(e) => setVeiculo({ ...veiculo, estado: e.target.value.toUpperCase() })} /></div>
          <div className="field"><label>Cidade</label><input value={veiculo.cidade} onChange={(e) => setVeiculo({ ...veiculo, cidade: e.target.value })} /></div>
        </div>
        <label style={{ fontSize: 13, display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={veiculo.motoristaEhProprietario} onChange={(e) => setVeiculo({ ...veiculo, motoristaEhProprietario: e.target.checked })} />
          Motorista e proprietario do veiculo
        </label>
        <button type="submit" className="btn-primary" style={{ alignSelf: "start" }}>Cadastrar Veiculo na Bsoft</button>
      </form>
    </div>
  );
}
