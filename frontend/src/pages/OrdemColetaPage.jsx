import { useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";
import { useContrato } from "../context/ContratoContext";
import { formatCPF, formatNome, formatPhone, formatPlaca } from "../utils/format";
import { CATEGORIAS_TRATORAS, ordenarVeiculosPorCategoria } from "../utils/vehicleCategory";

const SUPPLIER_LABEL = { AFL: "Fertimaxi", HERINGER: "Heringer" };
function cleanOcrValue(value) {
  const text = String(value || "").trim();
  return ["nao encontrado", "não encontrado", "nao encontrada", "não encontrada"].includes(text.toLowerCase()) ? "" : text;
}

export default function OrdemColetaPage() {
  const { selectedRows, metrics, dataCarregamento, supplier, motorista, updateMotorista, limparMotorista } = useContrato();
  const { nome, cpf, cnh, fone, placa1, placa2, placa3, roteiro, localizador, contatoCliente, observacoes, agendamentoId } = motorista;
  const [status, setStatus] = useState("Importe os documentos e revise os dados antes de gerar a O.C.");
  const [error, setError] = useState(""); const [loadingAction, setLoadingAction] = useState("");

  function buildPayload() {
    return { template: supplier, produtos: selectedRows.map((r) => ({ contrato:r.contrato, produto:r.produto, embalagem:r.embalagem, toneladas:String(r.toneladas), cidade:r.cidade, cliente:r.cliente, pedido_id:r.pedidoId||undefined })), cpf, nome, cnh, fone, placa1, placa2, placa3, data_carregamento:dataCarregamento, observacoes, agendamento_id:agendamentoId };
  }
  async function handleImportCnh(e) {
    const file=e.target.files?.[0]; e.target.value=""; if(!file)return; setError("");
    setLoadingAction("cnh"); setStatus("Lendo a CNH, isso pode levar alguns segundos...");
    try { const data=await api.ocrCnh(file); updateMotorista("nome",formatNome(cleanOcrValue(data.nome))); updateMotorista("cpf",formatCPF(cleanOcrValue(data.cpf))); updateMotorista("cnh",cleanOcrValue(data.numero)); setStatus(`CNH importada com sucesso de ${file.name}.`); }
    catch(err){ setError(`Erro ao ler CNH: ${err.message}`); }
    finally { setLoadingAction(""); }
  }
  async function handleImportCrlv(e) {
    const files=Array.from(e.target.files||[]); e.target.value=""; if(!files.length)return; setError("");
    setLoadingAction("crlv"); setStatus(files.length>1?`Lendo ${files.length} CRLVs, isso pode levar alguns segundos...`:"Lendo o CRLV, isso pode levar alguns segundos...");
    try {
      const resultados = await Promise.all(files.map((file)=>api.ocrCrlv(file).catch((err)=>({__erro:err.message}))));
      const erros = resultados.filter((r)=>r.__erro);
      const validos = resultados.filter((r)=>!r.__erro && cleanOcrValue(r.placa)).map((r)=>({...r, categoria_veiculo: cleanOcrValue(r.categoria_veiculo).toUpperCase()}));
      const ordenados = ordenarVeiculosPorCategoria(validos);
      if(!ordenados.length){ setError(erros.length?`Nenhuma placa foi encontrada. Falha ao ler ${erros.length} arquivo(s).`:"Nenhuma placa foi encontrada no(s) CRLV(s)."); return; }
      let novaPlaca1=placa1, novaPlaca2=placa2, novaPlaca3=placa3; const destinos=[];
      for(const dado of ordenados){
        const value=formatPlaca(cleanOcrValue(dado.placa));
        if(categoryIsTruck(dado.categoria_veiculo)){ novaPlaca1=value; destinos.push("cavalo"); }
        else if(!novaPlaca2){ novaPlaca2=value; destinos.push("primeira carreta"); }
        else if(!novaPlaca3){ novaPlaca3=value; destinos.push("segunda carreta"); }
      }
      updateMotorista("placa1",novaPlaca1); updateMotorista("placa2",novaPlaca2); updateMotorista("placa3",novaPlaca3);
      setStatus(`CRLV importado para: ${destinos.join(", ")}.${erros.length?` (${erros.length} arquivo(s) falharam)`:""}`);
    }
    catch(err){ setError(`Erro ao ler CRLV: ${err.message}`); }
    finally { setLoadingAction(""); }
  }
  function categoryIsTruck(category){ return CATEGORIAS_TRATORAS.has(category); }
  async function handleGerar(){ setError(""); if(!selectedRows.length){setError("Selecione os contratos antes de gerar a O.C.");return;} if(!nome.trim()){setError("O nome do motorista é obrigatório.");return;} setLoadingAction("pdf"); try{const payload=buildPayload();const result=await api.gerarOrdemColeta(payload);if(result?.agendamentoId)updateMotorista("agendamentoId",result.agendamentoId);if(supplier!=="HERINGER"){await api.gerarAutorizacaoColeta({...payload,agendamento_id:result?.agendamentoId??agendamentoId});setStatus("O.C. e autorização de coleta geradas com sucesso.");}else setStatus("O.C. gerada com sucesso.");}catch(err){setError(err.message);}finally{setLoadingAction("");} }
  async function handleEnviarEmail(){ setError(""); if(!selectedRows.length){setError("Selecione os contratos antes de enviar a O.C.");return;} if(!nome.trim()){setError("O nome do motorista é obrigatório.");return;} setLoadingAction("email"); try{const result=await api.enviarOrdemColetaEmail({...buildPayload(),roteiro,localizador,contato_cliente:contatoCliente});if(result?.agendamento_id)updateMotorista("agendamentoId",result.agendamento_id);setStatus(`E-mail enviado e agendamento #${result.agendamento_id} registrado.`);}catch(err){setError(err.message);}finally{setLoadingAction("");} }
  function handleLimpar(){limparMotorista();setStatus("Campos limpos. Importe novamente CNH e CRLV se necessário.");setError("");}

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
          <div className="field field-wide"><label>Nome do motorista *</label><input value={nome} onChange={(e)=>updateMotorista("nome",formatNome(e.target.value))} placeholder="Nome completo"/></div>
          <div className="field"><label>CPF</label><input value={cpf} onChange={(e)=>updateMotorista("cpf",formatCPF(e.target.value))} placeholder="000.000.000-00" maxLength={14}/></div>
          <div className="field"><label>CNH</label><input value={cnh} onChange={(e)=>updateMotorista("cnh",e.target.value)} placeholder="Número da CNH"/></div>
          <div className="field"><label>Telefone</label><input value={fone} onChange={(e)=>updateMotorista("fone",formatPhone(e.target.value))} placeholder="(00) 9 0000-0000"/></div>
          <div className="field"><label>Placa cavalo</label><input value={placa1} onChange={(e)=>updateMotorista("placa1",formatPlaca(e.target.value))} placeholder="ABC-1D23"/></div>
          <div className="field"><label>Placa carreta 1</label><input value={placa2} onChange={(e)=>updateMotorista("placa2",formatPlaca(e.target.value))} placeholder="ABC-1D23"/></div>
          <div className="field"><label>Placa carreta 2</label><input value={placa3} onChange={(e)=>updateMotorista("placa3",formatPlaca(e.target.value))} placeholder="ABC-1D23"/></div>
        </div>
      </section>
      <aside className="document-panel">
        <div className="panel-label">IMPORTAÇÃO INTELIGENTE</div>
        <label className={`upload-zone ${loadingAction==="cnh"?"loading":""}`}><span className="upload-icon"><Icon name="upload"/></span><div><strong>{loadingAction==="cnh"?"Processando...":"Importar CNH"}</strong><small>PDF, JPG ou PNG</small></div><Icon name="chevron" size={15}/><input type="file" accept=".pdf,.jpg,.jpeg,.png,.bmp" onChange={handleImportCnh} disabled={!!loadingAction}/></label>
        <label className={`upload-zone ${loadingAction==="crlv"?"loading":""}`}><span className="upload-icon"><Icon name="upload"/></span><div><strong>{loadingAction==="crlv"?"Processando...":"Importar CRLV"}</strong><small>Pode selecionar vários arquivos de uma vez</small></div><Icon name="chevron" size={15}/><input type="file" accept=".pdf,.jpg,.jpeg,.png,.bmp" multiple onChange={handleImportCrlv} disabled={!!loadingAction}/></label>
        <div className="document-tip"><Icon name="shield"/><p><strong>Leitura automática</strong><span>Revise os dados extraídos antes de gerar os documentos.</span></p></div>
      </aside>
    </div>
    <section className="card section-card">
      <div className="section-heading"><div><span className="section-index">02</span><div><h2>Entrega e observações</h2><p>Informações complementares para o cliente e a operação.</p></div></div></div>
      <div className="field-grid route-grid"><div className="field"><label>Localizador</label><input value={localizador} onChange={(e)=>updateMotorista("localizador",e.target.value)} placeholder="Código ou referência"/></div><div className="field"><label>Contato do cliente</label><input value={contatoCliente} onChange={(e)=>updateMotorista("contatoCliente",e.target.value)} placeholder="Nome ou telefone"/></div><div className="field field-wide"><label style={{display:"flex",alignItems:"center",gap:6}}><Icon name="route" size={12}/>Roteiro</label><input value={roteiro} onChange={(e)=>updateMotorista("roteiro",e.target.value)} placeholder="Detalhes do roteiro de entrega"/></div><div className="field field-full"><label>Observações</label><textarea value={observacoes} onChange={(e)=>updateMotorista("observacoes",e.target.value)} placeholder="Observações que aparecerão na O.C." rows={3}/></div></div>
    </section>
    {status&&<div className="inline-alert info"><span className="status-dot"/>{status}</div>}{error&&<div className="inline-alert error">{error}</div>}
    <div className="action-dock"><div><span>ETAPA FINAL</span><strong>{hasContracts && hasDriver ? "Tudo pronto para emitir" : "Conclua as etapas anteriores para emitir"}</strong></div><div className="action-buttons"><button className="btn-ghost" disabled={!!loadingAction} onClick={handleLimpar}><Icon name="trash" size={16}/>Limpar</button><button className="btn-secondary" disabled={!!loadingAction || !hasContracts || !hasDriver} onClick={handleEnviarEmail}><Icon name="mail" size={16}/>{loadingAction==="email"?"Enviando...":"Enviar por e-mail"}</button><button className="btn-primary" disabled={!!loadingAction || !hasContracts || !hasDriver} onClick={handleGerar}><Icon name="file" size={16}/>{loadingAction==="pdf"?"Gerando...":"Gerar O.C. em PDF"}</button></div></div>
  </div>;
}
