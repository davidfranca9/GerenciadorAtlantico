import { useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";
import { useContrato } from "../context/ContratoContext";
import { formatCPF, formatNome, formatPhone, formatPlaca } from "../utils/format";

const SUPPLIER_LABEL = { AFL: "Fertimax", HERINGER: "Heringer" };
const CATEGORIAS_TRATORAS = new Set(["CAVALO", "TRUCK", "CAVALO 4 EIXOS", "CAVALO TRUCADO 3 EIXOS", "BITRUCK", "TOCO", "3/4", "VAN", "AUTOMÓVEIS"]);
function cleanOcrValue(value) {
  const text = String(value || "").trim();
  return ["nao encontrado", "não encontrado", "nao encontrada", "não encontrada"].includes(text.toLowerCase()) ? "" : text;
}

export default function OrdemColetaPage() {
  const { selectedRows, metrics, dataCarregamento, supplier } = useContrato();
  const [nome, setNome] = useState(""); const [cpf, setCpf] = useState(""); const [cnh, setCnh] = useState(""); const [fone, setFone] = useState("");
  const [placa1, setPlaca1] = useState(""); const [placa2, setPlaca2] = useState(""); const [placa3, setPlaca3] = useState("");
  const [roteiro, setRoteiro] = useState(""); const [localizador, setLocalizador] = useState(""); const [contatoCliente, setContatoCliente] = useState("");
  const [observacoes, setObservacoes] = useState(""); const [agendamentoId, setAgendamentoId] = useState(null);
  const [status, setStatus] = useState("Importe os documentos e revise os dados antes de gerar a O.C.");
  const [error, setError] = useState(""); const [loadingAction, setLoadingAction] = useState("");

  function buildPayload() {
    return { template: supplier, produtos: selectedRows.map((r) => ({ contrato:r.contrato, produto:r.produto, embalagem:r.embalagem, toneladas:String(r.toneladas), cidade:r.cidade, cliente:r.cliente })), cpf, nome, cnh, fone, placa1, placa2, placa3, data_carregamento:dataCarregamento, observacoes, agendamento_id:agendamentoId };
  }
  async function handleImportCnh(e) {
    const file=e.target.files?.[0]; e.target.value=""; if(!file)return; setError("");
    setLoadingAction("cnh"); setStatus("Lendo a CNH, isso pode levar alguns segundos...");
    try { const data=await api.ocrCnh(file); setNome(formatNome(cleanOcrValue(data.nome))); setCpf(formatCPF(cleanOcrValue(data.cpf))); setCnh(cleanOcrValue(data.numero)); setStatus(`CNH importada com sucesso de ${file.name}.`); }
    catch(err){ setError(`Erro ao ler CNH: ${err.message}`); }
    finally { setLoadingAction(""); }
  }
  async function handleImportCrlv(e) {
    const file=e.target.files?.[0]; e.target.value=""; if(!file)return; setError("");
    setLoadingAction("crlv"); setStatus("Lendo o CRLV, isso pode levar alguns segundos...");
    try { const data=await api.ocrCrlv(file); const placa=cleanOcrValue(data.placa); const categoria=cleanOcrValue(data.categoria_veiculo).toUpperCase(); if(!placa){setError("Nenhuma placa foi encontrada no CRLV.");return;} const value=formatPlaca(placa); if(categoryIsTruck(categoria)){setPlaca1(value);setStatus("CRLV importado para a placa do cavalo.");}else if(!placa2){setPlaca2(value);setStatus("CRLV importado para a primeira carreta.");}else{setPlaca3(value);setStatus("CRLV importado para a segunda carreta.");} }
    catch(err){ setError(`Erro ao ler CRLV: ${err.message}`); }
    finally { setLoadingAction(""); }
  }
  function categoryIsTruck(category){ return CATEGORIAS_TRATORAS.has(category); }
  async function handleGerar(){ setError(""); if(!selectedRows.length){setError("Selecione os contratos antes de gerar a O.C.");return;} if(!nome.trim()){setError("O nome do motorista é obrigatório.");return;} setLoadingAction("pdf"); try{const payload=buildPayload();const result=await api.gerarOrdemColeta(payload);if(result?.agendamentoId)setAgendamentoId(result.agendamentoId);if(supplier!=="HERINGER"){await api.gerarAutorizacaoColeta({...payload,agendamento_id:result?.agendamentoId??agendamentoId});setStatus("O.C. e autorização de coleta geradas com sucesso.");}else setStatus("O.C. gerada com sucesso.");}catch(err){setError(err.message);}finally{setLoadingAction("");} }
  async function handleEnviarEmail(){ setError(""); if(!selectedRows.length){setError("Selecione os contratos antes de enviar a O.C.");return;} if(!nome.trim()){setError("O nome do motorista é obrigatório.");return;} setLoadingAction("email"); try{const result=await api.enviarOrdemColetaEmail({...buildPayload(),roteiro,localizador,contato_cliente:contatoCliente});if(result?.agendamento_id)setAgendamentoId(result.agendamento_id);setStatus(`E-mail enviado e agendamento #${result.agendamento_id} registrado.`);}catch(err){setError(err.message);}finally{setLoadingAction("");} }
  function handleLimpar(){setNome("");setCpf("");setCnh("");setFone("");setPlaca1("");setPlaca2("");setPlaca3("");setRoteiro("");setLocalizador("");setContatoCliente("");setObservacoes("");setAgendamentoId(null);setStatus("Campos limpos. Importe novamente CNH e CRLV se necessário.");setError("");}

  const preview=selectedRows.slice(0,3).map((r)=>`Pedido ${r.contrato||"-"} · ${r.produto||"Produto"} · ${r.toneladas||0} t${r.cidade?` · ${r.cidade}`:""}`);
  if(selectedRows.length>3)preview.push(`+ ${selectedRows.length-3} item(ns)`);
  const summary=[["Fornecedor",SUPPLIER_LABEL[supplier]||supplier,"truck"],["Carregamento",dataCarregamento||"Não definido","calendar"],["Pedidos",new Set(selectedRows.map((r)=>r.contrato).filter(Boolean)).size,"contract"],["Produtos",metrics.selectedCount,"clipboard"]];
  const hasContracts = selectedRows.length > 0;
  const hasDriver = Boolean(nome.trim());
  const workflow = [
    { label:"Selecionar contratos", state:hasContracts ? "done" : "current" },
    { label:"Conferir motorista", state:!hasContracts ? "locked" : hasDriver ? "done" : "current" },
    { label:"Emitir documentos", state:hasContracts && hasDriver ? "current" : "locked" },
  ];

  return <div className="ops-page">
    <div className="workflow-steps">{workflow.map((step,index)=><div className={`workflow-step ${step.state}`} key={step.label}><span>{step.state==="done"?"✓":index+1}</span><div><small>ETAPA {index+1}</small><strong>{step.label}</strong></div></div>)}</div>
    <div className="metric-grid">{summary.map(([label,value,icon])=><div className="metric-card" key={label}><span className="metric-icon"><Icon name={icon}/></span><div><small>{label}</small><strong>{value}</strong></div></div>)}</div>
    <div className="ops-content-grid">
      <section className="card section-card">
        <div className="section-heading"><div><span className="section-index">01</span><div><h2>Motorista e conjunto</h2><p>Preencha manualmente ou importe os documentos ao lado.</p></div></div><span className="required-note">* Campos obrigatórios</span></div>
        {selectedRows.length?<div className="selection-preview"><Icon name="contract"/><span>{preview.join("  •  ")}</span></div>:<div className="inline-alert warning">Selecione os contratos antes de emitir a ordem de coleta.</div>}
        <div className="field-grid driver-grid">
          <div className="field field-wide"><label>Nome do motorista *</label><input value={nome} onChange={(e)=>setNome(formatNome(e.target.value))} placeholder="Nome completo"/></div>
          <div className="field"><label>CPF</label><input value={cpf} onChange={(e)=>setCpf(formatCPF(e.target.value))} placeholder="000.000.000-00" maxLength={14}/></div>
          <div className="field"><label>CNH</label><input value={cnh} onChange={(e)=>setCnh(e.target.value)} placeholder="Número da CNH"/></div>
          <div className="field"><label>Telefone</label><input value={fone} onChange={(e)=>setFone(formatPhone(e.target.value))} placeholder="(00) 9 0000-0000"/></div>
          <div className="field"><label>Placa cavalo</label><input value={placa1} onChange={(e)=>setPlaca1(formatPlaca(e.target.value))} placeholder="ABC-1D23"/></div>
          <div className="field"><label>Placa carreta 1</label><input value={placa2} onChange={(e)=>setPlaca2(formatPlaca(e.target.value))} placeholder="ABC-1D23"/></div>
          <div className="field"><label>Placa carreta 2</label><input value={placa3} onChange={(e)=>setPlaca3(formatPlaca(e.target.value))} placeholder="ABC-1D23"/></div>
        </div>
      </section>
      <aside className="document-panel">
        <div className="panel-label">IMPORTAÇÃO INTELIGENTE</div>
        <label className={`upload-zone ${loadingAction==="cnh"?"loading":""}`}><span className="upload-icon"><Icon name="upload"/></span><div><strong>{loadingAction==="cnh"?"Processando...":"Importar CNH"}</strong><small>PDF, JPG ou PNG</small></div><Icon name="chevron" size={15}/><input type="file" accept=".pdf,.jpg,.jpeg,.png,.bmp" onChange={handleImportCnh} disabled={!!loadingAction}/></label>
        <label className={`upload-zone ${loadingAction==="crlv"?"loading":""}`}><span className="upload-icon"><Icon name="upload"/></span><div><strong>{loadingAction==="crlv"?"Processando...":"Importar CRLV"}</strong><small>Preenche a próxima placa livre</small></div><Icon name="chevron" size={15}/><input type="file" accept=".pdf,.jpg,.jpeg,.png,.bmp" onChange={handleImportCrlv} disabled={!!loadingAction}/></label>
        <div className="document-tip"><Icon name="shield"/><p><strong>Leitura automática</strong><span>Revise os dados extraídos antes de gerar os documentos.</span></p></div>
      </aside>
    </div>
    <section className="card section-card">
      <div className="section-heading"><div><span className="section-index">02</span><div><h2>Entrega e observações</h2><p>Informações complementares para o cliente e a operação.</p></div></div><Icon name="route"/></div>
      <div className="field-grid route-grid"><div className="field"><label>Localizador</label><input value={localizador} onChange={(e)=>setLocalizador(e.target.value)} placeholder="Código ou referência"/></div><div className="field"><label>Contato do cliente</label><input value={contatoCliente} onChange={(e)=>setContatoCliente(e.target.value)} placeholder="Nome ou telefone"/></div><div className="field field-wide"><label>Roteiro</label><input value={roteiro} onChange={(e)=>setRoteiro(e.target.value)} placeholder="Detalhes do roteiro de entrega"/></div><div className="field field-full"><label>Observações</label><textarea value={observacoes} onChange={(e)=>setObservacoes(e.target.value)} placeholder="Observações que aparecerão na O.C." rows={3}/></div></div>
    </section>
    {status&&<div className="inline-alert info"><span className="status-dot"/>{status}</div>}{error&&<div className="inline-alert error">{error}</div>}
    <div className="action-dock"><div><span>ETAPA FINAL</span><strong>{hasContracts && hasDriver ? "Tudo pronto para emitir" : "Conclua as etapas anteriores para emitir"}</strong></div><div className="action-buttons"><button className="btn-ghost" disabled={!!loadingAction} onClick={handleLimpar}><Icon name="trash" size={16}/>Limpar</button><button className="btn-secondary" disabled={!!loadingAction || !hasContracts || !hasDriver} onClick={handleEnviarEmail}><Icon name="mail" size={16}/>{loadingAction==="email"?"Enviando...":"Enviar por e-mail"}</button><button className="btn-primary" disabled={!!loadingAction || !hasContracts || !hasDriver} onClick={handleGerar}><Icon name="file" size={16}/>{loadingAction==="pdf"?"Gerando...":"Gerar O.C. em PDF"}</button></div></div>
  </div>;
}
