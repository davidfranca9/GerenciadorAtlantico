import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api/client";
import Icon from "../components/Icon";
import { formatCpfCnpj, formatPhone } from "../utils/format";
import "./clientes.css";

const VAZIO = { nome: "", cnpj_cpf: "", cidade: "", uf: "", contato: "", email: "", telefone: "", roteiro: "", localizacao: "", observacoes: "" };

const CAPITAIS_POR_UF = {
  AC: "Rio Branco", AL: "Maceió", AP: "Macapá", AM: "Manaus", BA: "Salvador", CE: "Fortaleza",
  DF: "Brasília", ES: "Vitória", GO: "Goiânia", MA: "São Luís", MT: "Cuiabá", MS: "Campo Grande",
  MG: "Belo Horizonte", PA: "Belém", PB: "João Pessoa", PR: "Curitiba", PE: "Recife", PI: "Teresina",
  RJ: "Rio de Janeiro", RN: "Natal", RS: "Porto Alegre", RO: "Porto Velho", RR: "Boa Vista",
  SC: "Florianópolis", SP: "São Paulo", SE: "Aracaju", TO: "Palmas",
};

function consultaLocalizacao(cliente) {
  return cliente.localizacao || [cliente.roteiro, cliente.cidade, cliente.uf].filter(Boolean).join(", ");
}

function extrairLinkMapa(cliente) {
  const texto = [cliente.localizacao, cliente.observacoes].filter(Boolean).join(" ");
  const encontrado = texto.match(/(?:https?:\/\/)?(?:www\.)?(?:google\.[^\s/]+\/maps[^\s]*|maps\.app\.goo\.gl\/[^\s]+|maps\.apple\.com\/[^\s]+|(?:www\.)?waze\.com\/[^\s]+)/i)?.[0];
  if (!encontrado) return "";
  const limpo = encontrado.replace(/[),.;]+$/, "");
  return /^https?:\/\//i.test(limpo) ? limpo : `https://${limpo}`;
}

function termoLocalizacao(cliente) {
  const link = extrairLinkMapa(cliente);
  const coordenadas = link.match(/[?&](?:q|query)=([^&]+)/i)?.[1];
  if (coordenadas) return decodeURIComponent(coordenadas);
  return consultaLocalizacao(cliente);
}

function linksMapa(cliente) {
  const consulta = encodeURIComponent(termoLocalizacao(cliente));
  return {
    apple: `https://maps.apple.com/?q=${consulta}`,
    waze: `https://www.waze.com/ul?q=${consulta}&navigate=yes`,
    google: `https://www.google.com/maps/search/?api=1&query=${consulta}`,
  };
}

function numeroWhatsapp(valor) {
  const digitos = String(valor || "").replace(/\D/g, "");
  return digitos.length === 10 || digitos.length === 11 ? `55${digitos}` : digitos;
}

function linkLocalizacao(cliente) {
  return extrairLinkMapa(cliente) || linksMapa(cliente).google;
}

function mensagemRoteiro(cliente) {
  return [
    `Olá! Seguem as informações do roteiro de ${cliente.nome}:`,
    cliente.roteiro && `Endereço: ${cliente.roteiro}`,
    consultaLocalizacao(cliente) && `Localização: ${linkLocalizacao(cliente)}`,
    cliente.observacoes && `Observações:\n${cliente.observacoes}`,
  ].filter(Boolean).join("\n\n");
}

export default function ClientesPage() {
  const navigate = useNavigate();
  const [clientes, setClientes] = useState([]);
  const [busca, setBusca] = useState("");
  const [form, setForm] = useState(VAZIO);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [cidadesPorUf, setCidadesPorUf] = useState(null);
  const [clienteAberto, setClienteAberto] = useState(null);
  const [numeroEnvio, setNumeroEnvio] = useState("");
  const [mensagemEnvio, setMensagemEnvio] = useState("");

  async function carregar() {
    try { setClientes(await api.listarClientes(busca || undefined)); } catch (err) { setError(err.message); }
  }

  useEffect(() => { carregar(); }, [busca]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.bsoftCidades().then(setCidadesPorUf).catch((err) => setError(err.message)); }, []);

  const cidadesDoEstado = useMemo(() => {
    if (!cidadesPorUf || !form.uf) return [];
    const nomes = (cidadesPorUf[form.uf] || []).map(([nome]) => nome);
    const capital = CAPITAIS_POR_UF[form.uf];
    const encontrouCapital = nomes.find((nome) => nome.toUpperCase() === (capital || "").toUpperCase());
    const resto = nomes.filter((nome) => nome.toUpperCase() !== (capital || "").toUpperCase()).sort();
    return encontrouCapital ? [encontrouCapital, ...resto] : resto;
  }, [cidadesPorUf, form.uf]);

  const updateField = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));
  const updateUf = (uf) => setForm((prev) => ({ ...prev, uf, cidade: "" }));

  function ajustarTextarea(e) {
    e.currentTarget.style.height = "auto";
    e.currentTarget.style.height = `${e.currentTarget.scrollHeight}px`;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      if (editingId) await api.atualizarCliente(editingId, form);
      else await api.criarCliente(form);
      setForm(VAZIO);
      setEditingId(null);
      carregar();
    } catch (err) { setError(err.message); }
  }

  function handleEdit(cliente) {
    setEditingId(cliente.id);
    setForm({
      nome: cliente.nome, cnpj_cpf: formatCpfCnpj(cliente.cnpj_cpf), cidade: cliente.cidade, uf: cliente.uf,
      contato: formatPhone(cliente.contato), email: cliente.email, telefone: formatPhone(cliente.telefone),
      roteiro: cliente.roteiro || "", localizacao: cliente.localizacao || "", observacoes: cliente.observacoes || "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleRemove(id) {
    if (!confirm("Remover este cliente?")) return;
    try { await api.removerCliente(id); carregar(); } catch (err) { setError(err.message); }
  }

  function abrirDetalhes(cliente) {
    setClienteAberto(cliente);
    setNumeroEnvio(cliente.contato || cliente.telefone || "");
    setMensagemEnvio(mensagemRoteiro(cliente));
  }

  function abrirNoChatWhatsapp() {
    const numero = numeroWhatsapp(numeroEnvio);
    if (!numero || !mensagemEnvio.trim()) return;
    navigate("/whatsapp", { state: { numero, texto: mensagemEnvio, nome: clienteAberto.nome, origem: "roteiro-cliente" } });
  }

  return (
    <div className="cli-pagina">
      <form onSubmit={handleSubmit} className="card cli-form">
        <div className="field-grid">
          <div className="field"><label>Nome*</label><input value={form.nome} onChange={(e) => updateField("nome", e.target.value)} required /></div>
          <div className="field"><label>CNPJ/CPF</label><input inputMode="numeric" value={form.cnpj_cpf} onChange={(e) => updateField("cnpj_cpf", formatCpfCnpj(e.target.value))} placeholder="000.000.000-00 ou 00.000.000/0000-00" /></div>
          <div className="field"><label>UF</label><select value={form.uf} onChange={(e) => updateUf(e.target.value)}><option value="">Selecione</option>{cidadesPorUf && Object.keys(cidadesPorUf).sort().map((uf) => <option key={uf} value={uf}>{uf}</option>)}</select></div>
          <div className="field"><label>Cidade</label><select value={form.cidade} onChange={(e) => updateField("cidade", e.target.value)}><option value="">Selecione</option>{cidadesDoEstado.map((cidade) => <option key={cidade} value={cidade}>{cidade === CAPITAIS_POR_UF[form.uf] ? `★ ${cidade} (Capital)` : cidade}</option>)}</select></div>
          <div className="field"><label>Contato Descarga</label><input inputMode="tel" value={form.contato} onChange={(e) => updateField("contato", formatPhone(e.target.value))} placeholder="(00) 9 9000-0000" /></div>
          <div className="field"><label>E-mail</label><input type="email" value={form.email} onChange={(e) => updateField("email", e.target.value)} placeholder="cliente@empresa.com" /></div>
          <div className="field"><label>Contato Contratante</label><input inputMode="tel" value={form.telefone} onChange={(e) => updateField("telefone", formatPhone(e.target.value))} placeholder="(00) 9 9000-0000" /></div>
        </div>
        <div className="field"><label>Roteiro (endereço)</label><input value={form.roteiro} onChange={(e) => updateField("roteiro", e.target.value)} placeholder="Endereço completo / roteiro de entrega" /></div>
        <div className="field">
          <label>Link de localização</label>
          <div className="cli-localizacao-campo"><Icon name="route" size={16} /><input value={form.localizacao} onChange={(e) => updateField("localizacao", e.target.value)} placeholder="Cole um link do Maps, Waze ou Apple Maps — ou informe o local" /></div>
          {(form.localizacao || form.roteiro) && <div className="cli-mapas"><a href={linkLocalizacao(form)} target="_blank" rel="noreferrer"><Icon name="route" size={13} /> Abrir localização no mapa</a></div>}
        </div>
        <div className="field"><label>Observações</label><textarea className="cli-observacoes" rows={2} value={form.observacoes} onInput={ajustarTextarea} onChange={(e) => updateField("observacoes", e.target.value)} placeholder="Digite livremente. Use Enter para separar as informações." /></div>
        <div className="cli-form-acoes"><button type="submit" className="btn-primary">{editingId ? "Salvar alterações" : "Cadastrar cliente"}</button>{editingId && <button type="button" className="btn-secondary" onClick={() => { setEditingId(null); setForm(VAZIO); }}>Cancelar edição</button>}</div>
      </form>

      <div className="field cli-busca"><label>Buscar por nome</label><input value={busca} onChange={(e) => setBusca(e.target.value)} /></div>
      {error && <div className="inline-alert error">{error}</div>}

      <div className="card cli-lista"><div className="cli-tabela"><table><thead><tr><th>Nome</th><th>CNPJ/CPF</th><th>Cidade/UF</th><th>Contato descarga</th><th>Localização</th><th></th></tr></thead><tbody>
        {clientes.map((cliente) => <tr key={cliente.id} className="cli-linha" tabIndex={0} onClick={() => abrirDetalhes(cliente)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") abrirDetalhes(cliente); }}><td><strong>{cliente.nome}</strong>{cliente.email && <small>{cliente.email}</small>}</td><td>{formatCpfCnpj(cliente.cnpj_cpf) || "—"}</td><td>{cliente.cidade}{cliente.uf ? `/${cliente.uf}` : ""}</td><td>{formatPhone(cliente.contato) || "—"}</td><td>{consultaLocalizacao(cliente) ? <div className="cli-mapas cli-mapas-tabela" onClick={(e) => e.stopPropagation()}><a href={linkLocalizacao(cliente)} target="_blank" rel="noreferrer"><Icon name="route" size={13} /> Mapa</a></div> : "—"}</td><td className="cli-acoes" onClick={(e) => e.stopPropagation()}><button className="btn-secondary" onClick={() => abrirDetalhes(cliente)}><Icon name="chat" size={13} /> Compartilhar</button><button className="btn-secondary" onClick={() => handleEdit(cliente)}>Editar</button><button className="btn-secondary" onClick={() => handleRemove(cliente.id)}>Remover</button></td></tr>)}
        {clientes.length === 0 && <tr><td colSpan={6} className="cli-vazio">Nenhum cliente cadastrado.</td></tr>}
      </tbody></table></div></div>

      {clienteAberto && <div className="cli-modal-fundo" onMouseDown={() => setClienteAberto(null)}>
        <section className="cli-detalhes" role="dialog" aria-modal="true" aria-labelledby="cli-detalhes-titulo" onMouseDown={(e) => e.stopPropagation()}>
          <div className="cli-detalhes-topo"><div><span>Detalhes do cliente</span><h2 id="cli-detalhes-titulo">{clienteAberto.nome}</h2></div><button type="button" className="cli-fechar" aria-label="Fechar" onClick={() => setClienteAberto(null)}>×</button></div>
          <div className="cli-detalhes-corpo">
            <div className="cli-dados-cliente">
              <div className="cli-detalhes-grid">
                <div><small>CPF/CNPJ</small><strong>{formatCpfCnpj(clienteAberto.cnpj_cpf) || "—"}</strong></div>
                <div><small>Cidade/UF</small><strong>{[clienteAberto.cidade, clienteAberto.uf].filter(Boolean).join("/") || "—"}</strong></div>
                <div><small>Contato descarga</small><strong>{formatPhone(clienteAberto.contato) || "—"}</strong></div>
                <div><small>Contato contratante</small><strong>{formatPhone(clienteAberto.telefone) || "—"}</strong></div>
                <div><small>E-mail</small><strong>{clienteAberto.email || "—"}</strong></div>
                <div className="cli-detalhe-largo"><small>Roteiro</small><strong>{clienteAberto.roteiro || "—"}</strong></div>
                {clienteAberto.observacoes && <div className="cli-detalhe-largo"><small>Observações</small><p>{clienteAberto.observacoes}</p></div>}
              </div>
              {consultaLocalizacao(clienteAberto) && <a className="btn-secondary cli-abrir-mapa" href={linkLocalizacao(clienteAberto)} target="_blank" rel="noreferrer"><Icon name="route" size={14} /> Abrir localização no mapa</a>}
            </div>

            <div className="cli-whatsapp">
              <div className="cli-whatsapp-titulo"><Icon name="chat" size={18} /><div><strong>Compartilhar pelo chat do sistema</strong><small>Escolha o número e revise a mensagem antes de abrir a conversa.</small></div></div>
              <div className="cli-numeros">
                {clienteAberto.contato && <label><input type="radio" name="numero-whatsapp" checked={numeroEnvio === clienteAberto.contato} onChange={() => setNumeroEnvio(clienteAberto.contato)} /><span>Descarga<strong>{formatPhone(clienteAberto.contato)}</strong></span></label>}
                {clienteAberto.telefone && <label><input type="radio" name="numero-whatsapp" checked={numeroEnvio === clienteAberto.telefone} onChange={() => setNumeroEnvio(clienteAberto.telefone)} /><span>Contratante<strong>{formatPhone(clienteAberto.telefone)}</strong></span></label>}
              </div>
              <div className="field"><label>Número que receberá a mensagem</label><input inputMode="tel" value={formatPhone(numeroEnvio)} onChange={(e) => setNumeroEnvio(formatPhone(e.target.value))} placeholder="(00) 9 9000-0000" /></div>
              <div className="field"><label>Mensagem do roteiro</label><textarea rows={8} value={mensagemEnvio} onChange={(e) => setMensagemEnvio(e.target.value)} /></div>
              <button type="button" className="btn-primary cli-enviar-whatsapp" disabled={!numeroEnvio || !mensagemEnvio.trim()} onClick={abrirNoChatWhatsapp}><Icon name="chat" size={15} /> Abrir conversa no WhatsApp</button>
            </div>
          </div>
        </section>
      </div>}
    </div>
  );
}
