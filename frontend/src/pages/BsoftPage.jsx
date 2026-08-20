import { useEffect, useState } from "react";
import * as api from "../api/client";
import DateField from "../components/DateField";
import { formatCEP, formatCNPJ, formatCPF, formatNome, formatPhone, formatPlaca } from "../utils/format";

const VEICULO_VAZIO = {
  placa: "", renavam: "", eixos: "", estado: "", cidade: "",
  marca: "", modelo: "", categoria: "", rodado: "", carroceria: "", equipamento: "",
};

const MOTORISTA_VAZIO = {
  nome: "", cpf: "", fone: "", dtNascimento: "", rntrc: "",
  cnh: { numero: "", seguro: "", categoria: "", protocolo: "", dtValidade: "", dtExpedicao: "", dtPrimeiraExpedicao: "" },
};

const ENDERECO_VAZIO = {
  cep: "", logradouro: "", numero: "", bairro: "", estado: "", cidade: "", complemento: "",
  inscricaoEstadual: "ISENTO", inscricaoMunicipal: "ISENTO", tipoEndereco: "Nacional",
  enderecoPreferencial: "Sim", cobrancaPreferencial: "Não", ieNaoContribuinte: "Sim",
};

const PROPRIETARIO_VAZIO = { cnpj: "", razao_social: "", rntrc: "", tipo: "", endereco_cnpj_data: {} };

const CATEGORIAS_TRATORAS = new Set([
  "CAVALO", "TRUCK", "CAVALO 4 EIXOS", "CAVALO TRUCADO 3 EIXOS", "BITRUCK", "TOCO", "3/4", "VAN", "AUTOMÓVEIS",
]);
const CATEGORIAS_REBOCADAS = new Set(["SEMI-REBOQUE 1", "SEMI-REBOQUE 2", "CARRETA", "DOLLY"]);

function ordenarVeiculosPorCategoria(veiculos) {
  const tratores = [];
  const reboques = [];
  const outros = [];
  for (const v of veiculos) {
    const categoria = (v.categoria_veiculo || "").trim().toUpperCase();
    if (CATEGORIAS_TRATORAS.has(categoria)) tratores.push(v);
    else if (CATEGORIAS_REBOCADAS.has(categoria)) reboques.push(v);
    else outros.push(v);
  }
  return [...tratores, ...reboques, ...outros].slice(0, 3);
}

function limparOcr(valor) {
  const texto = String(valor || "").trim();
  const lower = texto.toLowerCase();
  if (["nao encontrado", "não encontrado", "nao encontrada", "não encontrada", "formato invalido", "formato inválido"].includes(lower)) return "";
  return texto;
}

function VeiculoSecao({ titulo, slot, onChange, lookups, cidadesPorUf, extra }) {
  function set(field, value) {
    onChange({ ...slot, [field]: value });
  }

  function setCategoria(categoria) {
    const next = { ...slot, categoria };
    const catId = lookups?.categorias_veiculo?.[categoria];
    if (catId != null) {
      const equipId = lookups.categoria_to_equipamento?.[catId];
      const equipNome = Object.entries(lookups.tipos_equipamento || {}).find(([, id]) => id === equipId)?.[0] || "";
      const rodadoId = lookups.categoria_id_to_rodado_id?.[catId] ?? "00";
      const rodadoNome = lookups.tipos_rodado?.[rodadoId] || "NÃO APLICÁVEL";
      next.equipamento = equipNome;
      next.rodado = rodadoNome;
      next.marca = "";
    }
    onChange(next);
  }

  const marcasDisponiveis = lookups?.categoria_to_marcas?.[slot.categoria] || [];
  const cidadesDisponiveis = (cidadesPorUf?.[slot.estado] || []).map(([nome]) => nome);

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12, background: "transparent", border: "1px solid var(--border-soft)", boxShadow: "none" }}>
      <strong style={{ fontSize: 13.5 }}>{titulo}</strong>
      {extra}
      <div className="field-grid">
        <div className="field"><label>Placa</label><input value={slot.placa} onChange={(e) => set("placa", formatPlaca(e.target.value))} placeholder="ABC-1D23" /></div>
        <div className="field"><label>RENAVAM</label><input value={slot.renavam} onChange={(e) => set("renavam", e.target.value)} /></div>
        <div className="field"><label>Qtd. Eixos</label><input value={slot.eixos} onChange={(e) => set("eixos", e.target.value)} /></div>
        <div className="field">
          <label>Categoria</label>
          <select value={slot.categoria} onChange={(e) => setCategoria(e.target.value)}>
            <option value="">Selecione</option>
            {lookups && Object.keys(lookups.categorias_veiculo).sort().map((nome) => (
              <option key={nome} value={nome}>{nome}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Marca</label>
          <select value={slot.marca} onChange={(e) => set("marca", e.target.value)}>
            <option value="">Selecione</option>
            {marcasDisponiveis.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="field"><label>Modelo</label><input value={slot.modelo} onChange={(e) => set("modelo", e.target.value)} /></div>
        <div className="field">
          <label>Estado</label>
          <select value={slot.estado} onChange={(e) => onChange({ ...slot, estado: e.target.value, cidade: "" })}>
            <option value="">Selecione</option>
            {cidadesPorUf && Object.keys(cidadesPorUf).sort().map((uf) => <option key={uf} value={uf}>{uf}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Cidade</label>
          <select value={slot.cidade} onChange={(e) => set("cidade", e.target.value)}>
            <option value="">Selecione</option>
            {cidadesDisponiveis.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Tipo Rodado</label>
          <select value={slot.rodado} onChange={(e) => set("rodado", e.target.value)}>
            <option value="">Selecione</option>
            {lookups && Object.values(lookups.tipos_rodado).map((nome) => <option key={nome} value={nome}>{nome}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Tipo Carroceria</label>
          <select value={slot.carroceria} onChange={(e) => set("carroceria", e.target.value)}>
            <option value="">Selecione</option>
            {lookups && Object.values(lookups.tipos_carroceria).map((nome) => <option key={nome} value={nome}>{nome}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Tipo de Equipamento</label>
          <select value={slot.equipamento} onChange={(e) => set("equipamento", e.target.value)}>
            <option value="">Selecione</option>
            {lookups && Object.keys(lookups.tipos_equipamento).sort().map((nome) => <option key={nome} value={nome}>{nome}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}

export default function BsoftPage() {
  const [lookups, setLookups] = useState(null);
  const [cidadesPorUf, setCidadesPorUf] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Fluxo pronto. Você pode importar a O.C., documentos ou preencher manualmente.");
  const [loadingAction, setLoadingAction] = useState("");
  const [resultado, setResultado] = useState(null);

  const [motorista, setMotorista] = useState(MOTORISTA_VAZIO);
  const [endereco, setEndereco] = useState(ENDERECO_VAZIO);
  const [motoristaEProprietario, setMotoristaEProprietario] = useState(true);
  const [proprietario, setProprietario] = useState(PROPRIETARIO_VAZIO);
  const [cavalo, setCavalo] = useState(VEICULO_VAZIO);
  const [reboque1Ativo, setReboque1Ativo] = useState(false);
  const [reboque2Ativo, setReboque2Ativo] = useState(false);
  const [reboque1, setReboque1] = useState(VEICULO_VAZIO);
  const [reboque2, setReboque2] = useState(VEICULO_VAZIO);

  useEffect(() => {
    api.bsoftLookups().then(setLookups).catch((err) => setError(err.message));
    api.bsoftCidades().then(setCidadesPorUf).catch((err) => setError(err.message));
  }, []);

  function handleLimpar() {
    setMotorista(MOTORISTA_VAZIO);
    setEndereco(ENDERECO_VAZIO);
    setMotoristaEProprietario(true);
    setProprietario(PROPRIETARIO_VAZIO);
    setCavalo(VEICULO_VAZIO);
    setReboque1(VEICULO_VAZIO);
    setReboque2(VEICULO_VAZIO);
    setReboque1Ativo(false);
    setReboque2Ativo(false);
    setResultado(null);
    setError("");
    setStatus("Campos limpos. Você pode importar a O.C., documentos ou preencher manualmente.");
  }

  async function handleImportarOC(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    try {
      const dados = await api.bsoftImportarOC(file);
      handleLimpar();
      setMotorista((prev) => ({
        ...prev,
        nome: limparOcr(dados.nome),
        cpf: formatCPF(limparOcr(dados.cpf)),
        fone: formatPhone(limparOcr(dados.fone)),
        cnh: { ...prev.cnh, numero: limparOcr(dados.cnh) },
      }));
      setCavalo((prev) => ({ ...prev, placa: formatPlaca(limparOcr(dados.placa_cavalo)) }));
      if (limparOcr(dados.placa_carreta1)) {
        setReboque1Ativo(true);
        setReboque1((prev) => ({ ...prev, placa: formatPlaca(dados.placa_carreta1) }));
      }
      if (limparOcr(dados.placa_carreta2)) {
        setReboque1Ativo(true);
        setReboque2Ativo(true);
        setReboque2((prev) => ({ ...prev, placa: formatPlaca(dados.placa_carreta2) }));
      }
      setStatus(`Dados da O.C. importados de ${file.name}.`);
    } catch (err) {
      setError(`Erro ao importar O.C.: ${err.message}`);
    }
  }

  async function handleImportarDocumentos(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (files.length === 0) return;
    setError("");
    setLoadingAction("docs");
    setStatus("Processando documentos com OCR...");
    try {
      const { motorista: dadosMotorista, veiculos: dadosVeiculos } = await api.bsoftImportarDocumentos(files);
      if (!dadosMotorista || Object.keys(dadosMotorista).length === 0) {
        if (!dadosVeiculos || dadosVeiculos.length === 0) {
          setStatus("Os documentos foram lidos, mas nenhum dado útil foi encontrado.");
          return;
        }
      }
      handleLimpar();
      if (dadosMotorista) {
        setMotorista((prev) => ({
          nome: limparOcr(dadosMotorista.nome) || prev.nome,
          cpf: formatCPF(limparOcr(dadosMotorista.cpf)) || prev.cpf,
          fone: prev.fone,
          dtNascimento: limparOcr(dadosMotorista.dtNascimento),
          rntrc: limparOcr(dadosMotorista.rntrc),
          cnh: {
            numero: limparOcr(dadosMotorista.numero),
            seguro: limparOcr(dadosMotorista.seguro),
            categoria: limparOcr(dadosMotorista.categoria),
            protocolo: limparOcr(dadosMotorista.protocolo),
            dtValidade: limparOcr(dadosMotorista.dtValidade),
            dtExpedicao: limparOcr(dadosMotorista.dtExpedicao),
            dtPrimeiraExpedicao: limparOcr(dadosMotorista.dtPrimeiraExpedicao),
          },
        }));
      }

      const slots = [
        { setter: setCavalo, categoriaFallback: "" },
        { setter: setReboque1, categoriaFallback: "SEMI-REBOQUE 1" },
        { setter: setReboque2, categoriaFallback: "SEMI-REBOQUE 2" },
      ];
      ordenarVeiculosPorCategoria(dadosVeiculos || []).forEach((dado, idx) => {
        if (idx === 1) setReboque1Ativo(true);
        if (idx === 2) { setReboque1Ativo(true); setReboque2Ativo(true); }
        const { setter, categoriaFallback } = slots[idx];
        const categoria = limparOcr(dado.categoria_veiculo) || categoriaFallback;
        setter({
          ...VEICULO_VAZIO,
          placa: formatPlaca(limparOcr(dado.placa)),
          renavam: limparOcr(dado.renavam),
          modelo: limparOcr(dado.modelo),
          eixos: limparOcr(dado.eixos),
          categoria,
          marca: limparOcr(dado.marca),
          carroceria: limparOcr(dado.tipo_carroceria),
          estado: limparOcr(dado.estado),
          cidade: limparOcr(dado.cidade),
        });
      });

      setStatus("Documentos processados e formulário preenchido.");
    } catch (err) {
      setError(`Erro no OCR: ${err.message}`);
    } finally {
      setLoadingAction("");
    }
  }

  async function handleCepBlur() {
    const digitos = endereco.cep.replace(/\D/g, "");
    if (digitos.length !== 8) return;
    setError("");
    setStatus("Consultando CEP...");
    try {
      const dados = await api.bsoftConsultaCep(digitos);
      setEndereco((prev) => ({
        ...prev,
        logradouro: dados.street || "",
        bairro: dados.neighborhood || "",
        estado: dados.state || "",
        cidade: dados.city || "",
        complemento: "",
      }));
      setStatus("Endereço preenchido pela consulta de CEP.");
    } catch (err) {
      setError(`Erro na consulta de CEP: ${err.message}`);
    }
  }

  async function handleCnpjLookup() {
    const digitos = proprietario.cnpj.replace(/\D/g, "");
    if (digitos.length !== 14) {
      setError("O CNPJ deve conter 14 dígitos.");
      return;
    }
    setError("");
    setLoadingAction("cnpj");
    setStatus("Consultando CNPJ...");
    try {
      const dados = await api.bsoftConsultaCnpj(digitos);
      setProprietario((prev) => ({ ...prev, razao_social: dados.razao_social || "", endereco_cnpj_data: dados }));
      setStatus("Razão social preenchida pela consulta de CNPJ.");
    } catch (err) {
      setError(`Erro na consulta de CNPJ: ${err.message}`);
    } finally {
      setLoadingAction("");
    }
  }

  async function handleCadastrarTudo() {
    setError("");
    setResultado(null);
    if (!motorista.nome.trim() || !motorista.cpf.trim()) {
      setError("O Nome e o CPF do motorista são obrigatórios.");
      return;
    }
    const temVeiculo = Boolean(cavalo.placa.trim()) || (reboque1Ativo && reboque1.placa.trim()) || (reboque2Ativo && reboque2.placa.trim());
    if (!temVeiculo) {
      const continuar = window.confirm("Nenhum veículo foi informado. Deseja continuar mesmo assim?");
      if (!continuar) return;
    }

    setLoadingAction("cadastrar");
    setStatus("1/5: Preparando dados...");
    try {
      const payload = {
        motorista,
        endereco,
        motorista_e_proprietario: motoristaEProprietario,
        proprietario: motoristaEProprietario ? PROPRIETARIO_VAZIO : proprietario,
        cavalo,
        reboque1: reboque1Ativo ? reboque1 : null,
        reboque2: reboque2Ativo ? reboque2 : null,
        permitir_sem_veiculo: !temVeiculo,
      };
      const resp = await api.bsoftCadastrarCompleto(payload);
      setResultado(resp);
      setStatus(resp.mensagem);
      if (!resp.ok) setError(resp.mensagem);
    } catch (err) {
      setError(err.message);
      setStatus("Falha no processo de cadastro.");
    } finally {
      setLoadingAction("");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <strong style={{ fontSize: 15 }}>Cadastro Bsoft TMS</strong>
        <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
          Importe a O.C., processe CNH/CRLV/RNTRC, complete o cadastro do proprietário e envie tudo para a Bsoft em um único fluxo.
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <label className="btn-secondary" style={{ cursor: "pointer" }}>
            Importar da O.C.
            <input type="file" accept=".docx,.pdf" onChange={handleImportarOC} style={{ display: "none" }} />
          </label>
          <label className="btn-secondary" style={{ cursor: "pointer" }}>
            {loadingAction === "docs" ? "Processando..." : "Importar Documentos"}
            <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.bmp" onChange={handleImportarDocumentos} style={{ display: "none" }} disabled={loadingAction === "docs"} />
          </label>
          <button className="btn-secondary" onClick={handleLimpar}>Limpar Campos</button>
        </div>
        {status && <div style={{ fontSize: 12.5, color: "var(--muted)" }}>{status}</div>}
        {error && <div style={{ fontSize: 12.5, color: "var(--danger)" }}>{error}</div>}
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <strong style={{ fontSize: 15 }}>Dados Pessoais e CNH do Motorista</strong>
        <div className="field-grid">
          <div className="field"><label>Nome Completo</label><input value={motorista.nome} onChange={(e) => setMotorista({ ...motorista, nome: formatNome(e.target.value) })} /></div>
          <div className="field"><label>CPF</label><input value={motorista.cpf} onChange={(e) => setMotorista({ ...motorista, cpf: formatCPF(e.target.value) })} maxLength={14} /></div>
          <div className="field"><label>Celular</label><input value={motorista.fone} onChange={(e) => setMotorista({ ...motorista, fone: formatPhone(e.target.value) })} /></div>
          <DateField label="Data de Nascimento" value={motorista.dtNascimento} onChange={(v) => setMotorista({ ...motorista, dtNascimento: v })} />
          <div className="field"><label>RNTRC do Motorista</label><input value={motorista.rntrc} onChange={(e) => setMotorista({ ...motorista, rntrc: e.target.value })} /></div>
          <div className="field"><label>Nº Registro CNH</label><input value={motorista.cnh.numero} onChange={(e) => setMotorista({ ...motorista, cnh: { ...motorista.cnh, numero: e.target.value } })} /></div>
          <div className="field"><label>Seguro CNH</label><input value={motorista.cnh.seguro} onChange={(e) => setMotorista({ ...motorista, cnh: { ...motorista.cnh, seguro: e.target.value } })} /></div>
          <div className="field"><label>Categoria CNH</label><input value={motorista.cnh.categoria} onChange={(e) => setMotorista({ ...motorista, cnh: { ...motorista.cnh, categoria: e.target.value.toUpperCase() } })} /></div>
          <div className="field"><label>Nº do Espelho</label><input value={motorista.cnh.protocolo} onChange={(e) => setMotorista({ ...motorista, cnh: { ...motorista.cnh, protocolo: e.target.value } })} /></div>
          <DateField label="Validade CNH" value={motorista.cnh.dtValidade} onChange={(v) => setMotorista({ ...motorista, cnh: { ...motorista.cnh, dtValidade: v } })} />
          <DateField label="Data de Emissão" value={motorista.cnh.dtExpedicao} onChange={(v) => setMotorista({ ...motorista, cnh: { ...motorista.cnh, dtExpedicao: v } })} />
          <DateField label="1ª Habilitação" value={motorista.cnh.dtPrimeiraExpedicao} onChange={(v) => setMotorista({ ...motorista, cnh: { ...motorista.cnh, dtPrimeiraExpedicao: v } })} />
        </div>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <strong style={{ fontSize: 15 }}>Endereço do Motorista</strong>
        <div className="field-grid">
          <div className="field"><label>CEP</label><input value={endereco.cep} onChange={(e) => setEndereco({ ...endereco, cep: formatCEP(e.target.value) })} onBlur={handleCepBlur} placeholder="00000-000" /></div>
          <div className="field"><label>Logradouro</label><input value={endereco.logradouro} onChange={(e) => setEndereco({ ...endereco, logradouro: e.target.value })} /></div>
          <div className="field"><label>Número</label><input value={endereco.numero} onChange={(e) => setEndereco({ ...endereco, numero: e.target.value })} /></div>
          <div className="field"><label>Bairro</label><input value={endereco.bairro} onChange={(e) => setEndereco({ ...endereco, bairro: e.target.value })} /></div>
          <div className="field">
            <label>Estado</label>
            <select value={endereco.estado} onChange={(e) => setEndereco({ ...endereco, estado: e.target.value, cidade: "" })}>
              <option value="">Selecione</option>
              {cidadesPorUf && Object.keys(cidadesPorUf).sort().map((uf) => <option key={uf} value={uf}>{uf}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Cidade</label>
            <select value={endereco.cidade} onChange={(e) => setEndereco({ ...endereco, cidade: e.target.value })}>
              <option value="">Selecione</option>
              {(cidadesPorUf?.[endereco.estado] || []).map(([nome]) => <option key={nome} value={nome}>{nome}</option>)}
            </select>
          </div>
          <div className="field"><label>Complemento</label><input value={endereco.complemento} onChange={(e) => setEndereco({ ...endereco, complemento: e.target.value })} /></div>
          <div className="field"><label>Inscrição Estadual</label><input value={endereco.inscricaoEstadual} onChange={(e) => setEndereco({ ...endereco, inscricaoEstadual: e.target.value })} /></div>
          <div className="field"><label>Inscrição Municipal</label><input value={endereco.inscricaoMunicipal} onChange={(e) => setEndereco({ ...endereco, inscricaoMunicipal: e.target.value })} /></div>
          <div className="field">
            <label>Tipo Endereço</label>
            <select value={endereco.tipoEndereco} onChange={(e) => setEndereco({ ...endereco, tipoEndereco: e.target.value })}>
              <option value="Nacional">Nacional</option>
              <option value="Estrangeiro">Estrangeiro</option>
            </select>
          </div>
          <div className="field">
            <label>Endereço Preferencial</label>
            <select value={endereco.enderecoPreferencial} onChange={(e) => setEndereco({ ...endereco, enderecoPreferencial: e.target.value })}>
              <option value="Sim">Sim</option>
              <option value="Não">Não</option>
            </select>
          </div>
          <div className="field">
            <label>Cobrança Preferencial</label>
            <select value={endereco.cobrancaPreferencial} onChange={(e) => setEndereco({ ...endereco, cobrancaPreferencial: e.target.value })}>
              <option value="Sim">Sim</option>
              <option value="Não">Não</option>
            </select>
          </div>
          <div className="field">
            <label>IE Não Contribuinte</label>
            <select value={endereco.ieNaoContribuinte} onChange={(e) => setEndereco({ ...endereco, ieNaoContribuinte: e.target.value })}>
              <option value="Sim">Sim</option>
              <option value="Não">Não</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <strong style={{ fontSize: 15 }}>Veículos</strong>
        <div style={{ fontSize: 12.5, color: "var(--muted)" }}>Cadastre o cavalo e, se necessário, habilite os reboques abaixo.</div>
        <div style={{ display: "flex", gap: 20 }}>
          <label style={{ fontSize: 13, display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={reboque1Ativo} onChange={(e) => { setReboque1Ativo(e.target.checked); if (!e.target.checked) { setReboque2Ativo(false); setReboque1(VEICULO_VAZIO); setReboque2(VEICULO_VAZIO); } }} />
            Adicionar Reboque 1 (Placa 2)
          </label>
          <label style={{ fontSize: 13, display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={reboque2Ativo} disabled={!reboque1Ativo} onChange={(e) => { setReboque2Ativo(e.target.checked); if (!e.target.checked) setReboque2(VEICULO_VAZIO); }} />
            Adicionar Reboque 2 (Placa 3)
          </label>
        </div>

        <VeiculoSecao titulo="Dados do Cavalo Mecânico (Placa 1)" slot={cavalo} onChange={setCavalo} lookups={lookups} cidadesPorUf={cidadesPorUf} />
        {reboque1Ativo && <VeiculoSecao titulo="Dados do Reboque 1 (Placa 2)" slot={reboque1} onChange={setReboque1} lookups={lookups} cidadesPorUf={cidadesPorUf} />}
        {reboque2Ativo && <VeiculoSecao titulo="Dados do Reboque 2 (Placa 3)" slot={reboque2} onChange={setReboque2} lookups={lookups} cidadesPorUf={cidadesPorUf} />}
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <strong style={{ fontSize: 15 }}>Proprietário do Veículo</strong>
          <label style={{ fontSize: 13, display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={motoristaEProprietario} onChange={(e) => setMotoristaEProprietario(e.target.checked)} />
            Motorista é o proprietário do(s) veículo(s)
          </label>
        </div>
        {!motoristaEProprietario && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ fontSize: 12.5, color: "var(--muted)" }}>Se o veículo estiver em nome de outra empresa, preencha os dados abaixo.</div>
            <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
              <div className="field" style={{ flex: 1, minWidth: 220 }}>
                <label>CPF / CNPJ do Proprietário</label>
                <input value={proprietario.cnpj} onChange={(e) => setProprietario({ ...proprietario, cnpj: formatCNPJ(e.target.value) })} placeholder="00.000.000/0000-00" />
              </div>
              <button type="button" className="btn-secondary" disabled={loadingAction === "cnpj"} onClick={handleCnpjLookup}>
                {loadingAction === "cnpj" ? "Buscando..." : "Buscar por CNPJ"}
              </button>
            </div>
            <div className="field-grid">
              <div className="field"><label>Razão Social / Nome</label><input value={proprietario.razao_social} onChange={(e) => setProprietario({ ...proprietario, razao_social: e.target.value })} /></div>
              <div className="field"><label>RNTRC do Proprietário</label><input value={proprietario.rntrc} onChange={(e) => setProprietario({ ...proprietario, rntrc: e.target.value })} /></div>
              <div className="field">
                <label>Tipo Transportadora (PJ)</label>
                <select value={proprietario.tipo} onChange={(e) => setProprietario({ ...proprietario, tipo: e.target.value })}>
                  <option value="">Selecione</option>
                  <option value="ETC">ETC</option>
                  <option value="CTC">CTC</option>
                  <option value="Equiparado">Equiparado</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <strong style={{ fontSize: 15 }}>Ação Final</strong>
        <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
          Campos mínimos: Nome e CPF do motorista. O restante pode ser importado da documentação.
        </div>
        <button className="btn-primary" style={{ alignSelf: "start" }} disabled={loadingAction === "cadastrar"} onClick={handleCadastrarTudo}>
          {loadingAction === "cadastrar" ? status : "Cadastrar Tudo na Bsoft"}
        </button>
        {resultado && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12.5 }}>
            {resultado.passos.map((p, idx) => (
              <div key={idx} style={{ color: p.ok ? "var(--success)" : "var(--danger)" }}>
                {p.ok ? "✓" : "✗"} {p.passo}: {p.mensagem}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
