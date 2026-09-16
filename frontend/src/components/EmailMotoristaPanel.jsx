import { useEffect, useState } from "react";
import * as api from "../api/client";
import { formatCPF, formatNome, formatPhone, formatPlaca } from "../utils/format";
import { MODELOS_VEICULO } from "../utils/vehicleCategory";

const MOTORISTA_VAZIO = {
  driver_name: "", driver_cpf: "", driver_phone: "", cnh: "",
  plate_cavalo: "", plate_carreta1: "", plate_carreta2: "", modelo_veiculo: "",
};
const ITEM_VAZIO = { pedidoId: "", toneladas: "" };
const TITULO = { inclusao: "INCLUSÃO DE PLACAS", substituicao: "SUBSTITUIÇÃO DE MOTORISTA" };

// A configuracao (destinos e texto pronto) nao muda durante o uso da tela.
let configCache = null;
function carregarConfig() {
  if (!configCache) {
    configCache = api.emailMotoristaConfig().catch((err) => {
      configCache = null;
      throw err;
    });
  }
  return configCache;
}

function parseNumero(texto) {
  const num = parseFloat(String(texto ?? "").replace(",", "."));
  return Number.isFinite(num) ? num : 0;
}

function formatTon(valor) {
  return parseNumero(valor).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

// Inclusao (agendamento sem motorista) ou substituicao (ja tinha). Grava o
// motorista, junta pedidos se precisar e manda um e-mail NOVO pra fabrica
// com texto pronto que da pra editar. Se o e-mail nao sair, nada e gravado.
export default function EmailMotoristaPanel({ agendamento, aoEnviar, aoFechar }) {
  // O tipo e decidido na abertura: depois de enviar, o agendamento passa a
  // ter motorista, mas este painel continua sendo o da inclusao feita.
  const [tipo] = useState(() => ((agendamento.driver_name || "").trim() ? "substituicao" : "inclusao"));
  const [config, setConfig] = useState(null);
  const [pedidos, setPedidos] = useState([]);
  const [form, setForm] = useState(() => ({
    ...MOTORISTA_VAZIO,
    modelo_veiculo: tipo === "inclusao" ? agendamento.modelo_veiculo || "" : "",
  }));
  const [novosItens, setNovosItens] = useState([]);
  const [assunto, setAssunto] = useState(null); // null = texto pronto
  const [mensagem, setMensagem] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    carregarConfig().then(setConfig).catch((err) => setErro(err.message));
    api.listarPedidos().then(setPedidos).catch(() => {});
  }, []);

  function atualizar(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  function atualizarItem(idx, mudancas) {
    setNovosItens((prev) => prev.map((it, i) => (i === idx ? { ...it, ...mudancas } : it)));
  }

  const itensNovosValidos = novosItens
    .map((it) => ({ it, pedido: pedidos.find((p) => String(p.id) === String(it.pedidoId)) }))
    .filter(({ it, pedido }) => pedido && parseNumero(it.toneladas) > 0);

  const numeros = [];
  [...(agendamento.itens || []).map((i) => i.pedido), ...itensNovosValidos.map(({ pedido }) => pedido.contrato)]
    .forEach((numero) => {
      const valor = String(numero || "").trim();
      if (valor && !numeros.includes(valor)) numeros.push(valor);
    });
  const pedidosTexto = numeros.join(" / ") || "s/nº";
  const dataCarregamento = agendamento.data_agendada || agendamento.loading_date || "";

  const assuntoPronto = `${TITULO[tipo]}: ${form.driver_name.trim() || "(nome do motorista)"} - Nº ${pedidosTexto}`;
  const mensagemPronta = config
    ? config.modelos[tipo]
      .replace("{pedidos}", pedidosTexto)
      .replace("{data_carregamento}", dataCarregamento ? `, com carregamento previsto para ${dataCarregamento}` : "")
      .replace("{motorista_anterior}", agendamento.driver_name || "o motorista anterior")
    : "";
  const assuntoFinal = assunto ?? assuntoPronto;
  const mensagemFinal = mensagem ?? mensagemPronta;

  const fabrica = (agendamento.supplier || "").toLowerCase() === "heringer" ? "Heringer" : "Fertimaxi";
  const destinosReais = config?.destinatarios?.[fabrica] || [];

  async function enviar() {
    setErro("");
    if (!form.driver_name.trim()) {
      setErro("Informe o nome do motorista.");
      return;
    }
    if (!form.plate_cavalo.trim()) {
      setErro("Informe a placa do cavalo.");
      return;
    }
    setEnviando(true);
    try {
      const resposta = await api.enviarEmailMotorista(agendamento.id, {
        tipo,
        ...form,
        novos_itens: itensNovosValidos.map(({ it, pedido }) => ({
          pedido_id: pedido.id,
          pedido: pedido.contrato,
          cliente: pedido.cliente,
          produto: pedido.produto,
          cidade: pedido.cidade,
          embalagem: pedido.embalagem,
          toneladas: parseNumero(it.toneladas),
        })),
        assunto: assuntoFinal,
        mensagem: mensagemFinal,
      });
      aoEnviar?.(resposta.email);
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  }

  const campo = (rotulo, nome, formatar, props = {}) => (
    <div className="field">
      <label>{rotulo}</label>
      <input value={form[nome]} onChange={(e) => atualizar(nome, formatar ? formatar(e.target.value) : e.target.value)} {...props} />
    </div>
  );

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14, margin: "6px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 15 }}>
          {tipo === "inclusao" ? "Incluir motorista e pedir inclusão de placas" : "Substituir motorista"}
        </strong>
        <button type="button" className="btn-ghost" onClick={aoFechar}>Fechar</button>
      </div>

      {config && (config.em_teste ? (
        <div className="inline-alert warning">
          Modo teste: este e-mail vai só para <strong>{config.email_teste}</strong>
          {config.copia ? ` (cópia para ${config.copia})` : ""}. Aprovado o teste, passa a ir para {destinosReais.join(", ")}.
        </div>
      ) : (
        <div className="inline-alert info">
          Vai para {destinosReais.join(", ")}{config.copia ? ` (cópia para ${config.copia})` : ""}.
        </div>
      ))}

      {tipo === "substituicao" && (
        <div className="inline-alert info">
          Motorista atual: <strong>{agendamento.driver_name}</strong>
          {agendamento.plate_cavalo ? ` · ${agendamento.plate_cavalo}` : ""}. Preencha abaixo quem entra no lugar.
        </div>
      )}

      <div className="field-grid">
        {campo(tipo === "inclusao" ? "Motorista *" : "Novo motorista *", "driver_name", formatNome)}
        {campo("CPF", "driver_cpf", formatCPF, { maxLength: 14, placeholder: "000.000.000-00" })}
        {campo("CNH", "cnh")}
        {campo("Telefone", "driver_phone", formatPhone)}
        {campo("Placa do cavalo *", "plate_cavalo", formatPlaca, { placeholder: "ABC-1D23" })}
        {campo("Placa da carreta 1", "plate_carreta1", formatPlaca, { placeholder: "ABC-1D23" })}
        {campo("Placa da carreta 2", "plate_carreta2", formatPlaca, { placeholder: "ABC-1D23" })}
        <div className="field">
          <label>Modelo do veículo</label>
          <select value={form.modelo_veiculo} onChange={(e) => atualizar("modelo_veiculo", e.target.value)}>
            <option value="">Selecione</option>
            {MODELOS_VEICULO.map((m) => <option key={m.valor} value={m.valor}>{m.rotulo}</option>)}
          </select>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong style={{ fontSize: 13 }}>Pedidos deste agendamento</strong>
        <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
          {(agendamento.itens || []).map((i) => `${i.pedido || "s/nº"} · ${i.cliente || "-"} · ${i.produto || "-"} · ${formatTon(i.toneladas)} t`).join("  •  ") || "Nenhum item."}
        </div>
        {novosItens.map((it, idx) => {
          const escolhido = pedidos.find((p) => String(p.id) === String(it.pedidoId));
          return (
            <div key={idx} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <select
                style={{ flex: "1 1 360px" }}
                value={it.pedidoId}
                onChange={(e) => {
                  const pedido = pedidos.find((p) => String(p.id) === e.target.value);
                  atualizarItem(idx, { pedidoId: e.target.value, toneladas: pedido ? String(pedido.toneladas_restante) : "" });
                }}
              >
                <option value="">Selecione o pedido que vai junto</option>
                {pedidos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.novo ? "NOVO · " : ""}{p.contrato || "s/nº"} · {p.cliente} · {p.produto} · {formatTon(p.toneladas_restante)} t restantes
                  </option>
                ))}
              </select>
              <input
                style={{ width: 110 }}
                value={it.toneladas}
                placeholder="Toneladas"
                title={escolhido ? `Máximo: ${formatTon(escolhido.toneladas_restante)} t` : ""}
                onChange={(e) => atualizarItem(idx, { toneladas: e.target.value })}
              />
              <button type="button" className="btn-ghost" onClick={() => setNovosItens((prev) => prev.filter((_, i) => i !== idx))}>
                Remover
              </button>
            </div>
          );
        })}
        <div>
          <button type="button" className="btn-secondary" onClick={() => setNovosItens((prev) => [...prev, { ...ITEM_VAZIO }])}>
            + Adicionar outro pedido junto
          </button>
        </div>
      </div>

      <div className="field">
        <label>Assunto</label>
        <input value={assuntoFinal} onChange={(e) => setAssunto(e.target.value)} />
      </div>
      <div className="field">
        <label>Texto do e-mail</label>
        <textarea rows={7} value={mensagemFinal} onChange={(e) => setMensagem(e.target.value)} style={{ resize: "vertical" }} />
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 12.5, color: "var(--muted)" }}>
        {(assunto !== null || mensagem !== null) && (
          <button type="button" className="btn-ghost" onClick={() => { setAssunto(null); setMensagem(null); }}>
            Voltar ao texto pronto
          </button>
        )}
        <span>
          Vão juntos no e-mail, automaticamente: os dados do motorista
          {tipo === "substituicao" ? ", os do motorista que sai" : ""}, a tabela dos pedidos e a autorização de carregamento em anexo.
        </span>
      </div>

      {erro && <div className="inline-alert error">{erro}</div>}

      <div style={{ display: "flex", gap: 10 }}>
        <button type="button" className="btn-primary" disabled={enviando || !config} onClick={enviar}>
          {enviando ? "Enviando..." : tipo === "inclusao" ? "Salvar e enviar inclusão" : "Salvar e enviar substituição"}
        </button>
      </div>
    </div>
  );
}
