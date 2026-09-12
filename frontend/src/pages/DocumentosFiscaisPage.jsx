import { useEffect, useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";

const PERIODOS = [
  { dias: 7, label: "7 dias" },
  { dias: 30, label: "30 dias" },
  { dias: 90, label: "90 dias" },
];

function formatarValor(valor) {
  const num = Number(valor);
  if (!Number.isFinite(num)) return "-";
  return num.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatarDataHora(texto) {
  if (!texto) return "-";
  const [data, hora] = String(texto).split(" ");
  const partes = (data || "").split("-");
  if (partes.length !== 3) return texto;
  return `${partes[2]}/${partes[1]}/${partes[0]}${hora ? ` ${hora.slice(0, 5)}` : ""}`;
}

const EMBALAGENS = ["GRANEL", "BIG BAG", "SACARIA"];

// Especies do cadastro do Bsoft, com os ids reais lidos do combo especieId
// da tela de emissao. A ordem e a mesma que aparece la.
const ESPECIES = [
  [1, "GRANEL"], [3, "SACOS"], [4, "FARDOS"], [5, "BIG BAG"], [6, "PALLETS"],
  [7, "CAIXAS"], [8, "SACO DE 50 KG"], [9, "Saco de 20kg"], [10, "BIG BAG 1000 KG"],
  [11, "SACO DE 25 KG"], [12, "SC X 25 KG"], [13, "Tonelada"], [14, "SACOS 50 KG"],
];

// De onde a NF-e vem. Sao tres porque a nota chega de tres jeitos: o
// arquivo que a fabrica mandou, a nota que o sistema ja coletou sozinho, e
// o DANFE na mao quando nao veio arquivo nenhum.
const ORIGENS = [
  { id: "xml", rotulo: "Enviar XML", dica: "O arquivo que a fábrica mandou" },
  { id: "recebida", rotulo: "Nota já recebida", dica: "Coletada do e-mail ou da SEFAZ" },
  { id: "manual", rotulo: "Digitar na mão", dica: "Quando não veio arquivo nenhum" },
];

// modFrete da NF-e: e o que define o tomador e quem paga o frete.
const MODALIDADES_FRETE = [
  ["0", "Por conta do remetente (CIF)"],
  ["1", "Por conta do destinatário (FOB)"],
  ["3", "Transporte próprio, conta do remetente"],
  ["4", "Transporte próprio, conta do destinatário"],
];

const UF_POR_CODIGO = {
  11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
  21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
  28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
  42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
};

// A chave de acesso nao e um numero opaco: o layout da NF-e reserva
// posicoes fixas pra UF, ano/mes, CNPJ do emitente, serie e numero. Abrir
// ela aqui mostra na hora se os 44 digitos foram copiados certo - e evita
// pedir de novo o que o proprio documento ja diz.
function abrirChave(texto) {
  const d = String(texto || "").replace(/\D/g, "");
  if (d.length !== 44) return null;
  return {
    uf: UF_POR_CODIGO[Number(d.slice(0, 2))] || "?",
    emitente: d.slice(6, 20),
    serie: d.slice(22, 25).replace(/^0+/, "") || "0",
    numero: d.slice(25, 34).replace(/^0+/, "") || "0",
    emissao: `${d.slice(4, 6)}/20${d.slice(2, 4)}`,
  };
}

function formatarCnpjCpf(texto) {
  const d = String(texto || "").replace(/\D/g, "").slice(0, 14);
  if (d.length <= 11) return formatarCpf(d);
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

function Secao({ titulo, children }) {
  return (
    <fieldset
      style={{
        border: "1px solid var(--border)", borderRadius: 8, padding: "12px 14px 14px",
        margin: 0, display: "flex", flexDirection: "column", gap: 10,
      }}
    >
      <legend style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: "var(--muted)", padding: "0 6px" }}>
        {titulo}
      </legend>
      {children}
    </fieldset>
  );
}

function Campo({ rotulo, valor, largura = 1 }) {
  return (
    <div style={{ flex: largura, minWidth: 120 }}>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>{rotulo}</div>
      <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2, wordBreak: "break-word" }}>{valor || "—"}</div>
    </div>
  );
}

function Linha({ children }) {
  return <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>{children}</div>;
}

// O campo de CPF tem 11 digitos; sem limite dava pra digitar 14 e o
// backend acabava procurando em pessoas juridicas.
function formatarCpf(texto) {
  const d = String(texto || "").replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

// Aceita os dois padroes de placa: ABC1234 e ABC1D23 (Mercosul).
function formatarPlaca(texto) {
  const limpo = String(texto || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 7);
  return limpo.length > 3 ? `${limpo.slice(0, 3)}-${limpo.slice(3)}` : limpo;
}

// Campo com lupa: procura no cadastro do Bsoft e deixa escolher o
// registro. E o que a tela deles faz nos campos vinculados.
function BuscaComLupa({ rotulo, placeholder, procurar, rotular, aoEscolher, escolhido }) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [aviso, setAviso] = useState("");

  async function buscar() {
    setBuscando(true);
    setAviso("");
    try {
      const dados = await procurar(termo);
      setResultados(dados.resultados || []);
      if (dados.aviso) setAviso(dados.aviso);
      else if (!dados.resultados?.length) setAviso("Nada encontrado no cadastro do Bsoft.");
    } catch (err) {
      setAviso(err.message);
    } finally {
      setBuscando(false);
    }
  }

  return (
    <div style={{ flex: 2, minWidth: 260 }}>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>{rotulo}</div>
      <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
        <input
          value={termo}
          placeholder={placeholder}
          onChange={(ev) => setTermo(ev.target.value)}
          onKeyDown={(ev) => { if (ev.key === "Enter") { ev.preventDefault(); buscar(); } }}
          style={{ flex: 1 }}
        />
        <button className="btn-secondary" type="button" onClick={buscar} disabled={buscando} title="Procurar no Bsoft">
          {buscando ? "..." : "🔍"}
        </button>
      </div>
      {escolhido && (
        <div style={{ fontSize: 12, marginTop: 4 }}>
          Selecionado: <strong>{escolhido}</strong>
        </div>
      )}
      {aviso && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>{aviso}</div>}
      {resultados?.length > 0 && (
        <div style={{ marginTop: 6, maxHeight: 170, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
          {resultados.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => { aoEscolher(r); setResultados(null); }}
              style={{
                display: "block", width: "100%", textAlign: "left", padding: "6px 10px",
                background: "none", border: "none", borderBottom: "1px solid var(--border)",
                cursor: "pointer", fontSize: 12.5,
              }}
            >
              {rotular(r)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Escolher({ rotulo, valor, opcoes, aoMudar }) {
  return (
    <div style={{ flex: 2, minWidth: 220 }}>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>{rotulo}</div>
      <select value={valor || ""} onChange={(e) => aoMudar(e.target.value)} style={{ width: "100%", marginTop: 2 }}>
        <option value="">Selecione</option>
        {opcoes.map((o) => <option key={o.id} value={o.id}>{o.descricao}</option>)}
      </select>
    </div>
  );
}

function Corrigir({ rotulo, valor, placeholder, aoMudar, formatar }) {
  return (
    <div style={{ flex: 1, minWidth: 140 }}>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>{rotulo}</div>
      <input
        value={valor || ""}
        placeholder={placeholder}
        onChange={(e) => aoMudar(formatar ? formatar(e.target.value) : e.target.value)}
        style={{ width: "100%", marginTop: 2 }}
      />
    </div>
  );
}

// Campo de digitacao simples, pra nota que entra na mao.
function CampoManual({ rotulo, campo, valores, aoMudar, placeholder, formatar, largura = 1, tipo = "text" }) {
  return (
    <div style={{ flex: largura, minWidth: 130 }}>
      <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>{rotulo}</div>
      <input
        type={tipo}
        value={valores[campo] || ""}
        placeholder={placeholder}
        onChange={(ev) => aoMudar(campo, formatar ? formatar(ev.target.value) : ev.target.value)}
        style={{ width: "100%", marginTop: 2 }}
      />
    </div>
  );
}

// A fila do que o sistema ja coletou sozinho, por e-mail ou pela SEFAZ.
// Quem opera so escolhe: a nota inteira ja esta guardada aqui.
function NotasRecebidas({ notas, carregando, chave, aoEscolher, aoRecarregar }) {
  const escolhida = notas.find((n) => n.chave === chave);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
        <div style={{ flex: 1, minWidth: 260 }}>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>
            Notas recebidas e ainda sem CT-e
          </div>
          <select value={chave} onChange={(ev) => aoEscolher(ev.target.value)} style={{ width: "100%", marginTop: 2 }}>
            <option value="">{carregando ? "Carregando..." : "Selecione a nota"}</option>
            {notas.map((n) => (
              <option key={n.chave} value={n.chave}>
                NF {n.numero}/{n.serie} · {n.emitente} → {n.destino} · {formatarValor(n.valor)} · {n.origem}
                {n.agendamento_id ? ` · ag. #${n.agendamento_id}` : ""}
              </option>
            ))}
          </select>
        </div>
        <button className="btn-secondary" type="button" onClick={aoRecarregar} title="Buscar de novo">
          ↻
        </button>
      </div>
      {escolhida?.casamento && (
        <div className={escolhida.agendamento_id ? "inline-alert info" : "inline-alert warning"} style={{ fontSize: 12 }}>
          {escolhida.agendamento_id
            ? `Casada com o agendamento #${escolhida.agendamento_id}: ${escolhida.casamento}.`
            : `Sem agendamento: ${escolhida.casamento}.`}
        </div>
      )}
      {!carregando && !notas.length && (
        <div style={{ fontSize: 12, color: "var(--muted)" }}>
          Nenhuma nota coletada ainda. Você também pode colar a chave de uma NF-e abaixo — ela é
          buscada na SEFAZ na hora.
        </div>
      )}
      <input
        value={chave}
        placeholder="Ou cole a chave de acesso (44 dígitos)"
        onChange={(ev) => aoEscolher(ev.target.value.replace(/\D/g, "").slice(0, 44))}
        style={{ width: "100%" }}
      />
    </div>
  );
}

// O DANFE transcrito. So entra aqui o que a chave de acesso nao carrega:
// emitente, serie e numero saem dela, e o municipio sai do endereco
// escolhido no cadastro do Bsoft.
function NotaManual({ valores, aoMudar }) {
  const daChave = abrirChave(valores.chave);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Linha>
        <CampoManual
          rotulo="Chave de acesso da NF-e" campo="chave" valores={valores} aoMudar={aoMudar}
          largura={3} placeholder="44 dígitos do DANFE"
          formatar={(t) => t.replace(/\D/g, "").slice(0, 44)}
        />
        <CampoManual rotulo="Emissão da nota" campo="emissao" valores={valores} aoMudar={aoMudar} tipo="date" />
      </Linha>

      {valores.chave && (
        <div className={daChave ? "inline-alert info" : "inline-alert warning"} style={{ fontSize: 12.5 }}>
          {daChave
            ? `A chave diz: NF ${daChave.numero}, série ${daChave.serie}, emitente ${formatarCnpjCpf(daChave.emitente)}, ${daChave.uf}, ${daChave.emissao}.`
            : `${valores.chave.length} de 44 dígitos.`}
        </div>
      )}

      <Linha>
        <CampoManual
          rotulo="CNPJ/CPF do destinatário" campo="destinatario_doc" valores={valores}
          aoMudar={aoMudar} largura={2} formatar={formatarCnpjCpf} placeholder="00.000.000/0000-00"
        />
        <div style={{ flex: 2, minWidth: 200 }}>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--muted)" }}>
            Modalidade do frete
          </div>
          <select
            value={valores.modalidade_frete || ""}
            onChange={(ev) => aoMudar("modalidade_frete", ev.target.value)}
            style={{ width: "100%", marginTop: 2 }}
          >
            <option value="">Selecione</option>
            {MODALIDADES_FRETE.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
          </select>
        </div>
      </Linha>

      <Linha>
        <CampoManual rotulo="Produto" campo="produto" valores={valores} aoMudar={aoMudar} largura={3} placeholder="UREIA PRILL 46% N" />
        <CampoManual rotulo="Peso (kg)" campo="peso_kg" valores={valores} aoMudar={aoMudar} placeholder="27000" />
        <CampoManual rotulo="Valor da nota" campo="valor_nota" valores={valores} aoMudar={aoMudar} placeholder="68850,00" />
        <CampoManual rotulo="Volumes" campo="quantidade" valores={valores} aoMudar={aoMudar} placeholder="540" />
      </Linha>

      <details>
        <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--muted)" }}>
          Valores fiscais da nota (saem impressos no DACTE)
        </summary>
        <Linha>
          <CampoManual rotulo="CFOP" campo="cfop" valores={valores} aoMudar={aoMudar} placeholder="6101" />
          <CampoManual rotulo="Base do ICMS" campo="base_icms" valores={valores} aoMudar={aoMudar} placeholder="22950,00" />
          <CampoManual rotulo="Valor do ICMS" campo="valor_icms" valores={valores} aoMudar={aoMudar} placeholder="2754,00" />
          <CampoManual rotulo="Marca" campo="marca" valores={valores} aoMudar={aoMudar} placeholder="Fertimaxi" />
        </Linha>
      </details>
    </div>
  );
}

const ROTULO_STATUS = {
  RASCUNHO: ["Rascunho", "#8a8f98"],
  ENVIANDO_CTE: ["Enviando", "#8a8f98"],
  CTE_CRIADO: ["Criado no Bsoft", "#2f6fa8"],
  CTE_PROCESSANDO: ["Aguardando SEFAZ", "#b7791f"],
  CTE_AUTORIZADO: ["Autorizado", "#2f9e6d"],
  CTE_REJEITADO: ["Rejeitado", "#c0392b"],
  CANCELADO: ["Cancelado", "#8a8f98"],
};

// O que aconteceu com cada CT-e depois do clique. O acompanhamento roda
// sozinho a cada 5 minutos e atualiza isto; a tela so mostra.
function OperacoesRecentes() {
  const [operacoes, setOperacoes] = useState([]);

  useEffect(() => {
    let vivo = true;
    function carregar() {
      api.fiscalListarOperacoes()
        .then((d) => { if (vivo) setOperacoes((Array.isArray(d) ? d : d.operacoes || []).slice(0, 12)); })
        .catch(() => {});
    }
    carregar();
    const timer = setInterval(carregar, 60000);
    return () => { vivo = false; clearInterval(timer); };
  }, []);

  if (!operacoes.length) return null;

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        <strong style={{ fontSize: 15 }}>Últimas emissões</strong>
        <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 4 }}>
          Acompanhadas sozinhas: o sistema pergunta ao Bsoft a cada 5 minutos o que a SEFAZ respondeu.
        </div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="table" style={{ fontSize: 12.5 }}>
          <thead>
            <tr><th>Op.</th><th>Agend.</th><th>CT-e</th><th>Situação</th><th>Chave</th><th>Observação</th></tr>
          </thead>
          <tbody>
            {operacoes.map((op) => {
              const [rotulo, cor] = ROTULO_STATUS[op.status] || [op.status, "#8a8f98"];
              return (
                <tr key={op.id}>
                  <td>#{op.id}</td>
                  <td>{op.agendamento_id ? `#${op.agendamento_id}` : "—"}</td>
                  <td>{op.cte_numero || (op.cod_conhecimento_bsoft ? `id ${op.cod_conhecimento_bsoft}` : "—")}</td>
                  <td>
                    <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, color: "#fff", background: cor }}>
                      {rotulo}
                    </span>
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>{op.cte_chave ? `…${op.cte_chave.slice(-8)}` : "—"}</td>
                  <td style={{ maxWidth: 360, whiteSpace: "normal" }}>{op.erro || op.cte_motivo_rejeicao || ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EmitirCte() {
  const [aberto, setAberto] = useState(false);
  const [agendamentos, setAgendamentos] = useState([]);
  const [agendamentoId, setAgendamentoId] = useState("");
  const [origemNota, setOrigemNota] = useState("xml");
  const [arquivo, setArquivo] = useState(null);
  const [chaveNfe, setChaveNfe] = useState("");
  const [notas, setNotas] = useState([]);
  const [carregandoNotas, setCarregandoNotas] = useState(false);
  const [manual, setManual] = useState({ modalidade_frete: "1" });
  const [tarifa, setTarifa] = useState("");
  const [aliquota, setAliquota] = useState("12");
  const [km, setKm] = useState("");
  const [embalagem, setEmbalagem] = useState("BIG BAG");
  const [especieId, setEspecieId] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("1");
  const [definitivo, setDefinitivo] = useState(false);
  const [escolhas, setEscolhas] = useState({});
  const [conjuntos, setConjuntos] = useState([]);
  const [sugestao, setSugestao] = useState(null);
  const [espelho, setEspelho] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!aberto || agendamentos.length) return;
    api.listarAgendamentos().then(setAgendamentos).catch(() => {});
    api.fiscalListarConjuntos()
      .then((d) => setConjuntos(d.conjuntos || []))
      .catch(() => {});
  }, [aberto, agendamentos.length]);

  // O agendamento escolhido traz a tarifa da ultima cotacao do destino e a
  // embalagem do pedido. Preenche so o que estiver vazio: o que a pessoa
  // ja digitou nao e sobrescrito.
  useEffect(() => {
    if (!agendamentoId) { setSugestao(null); return; }
    let vivo = true;
    api.fiscalSugestoes(agendamentoId)
      .then((d) => {
        if (!vivo) return;
        setSugestao(d);
        if (d.tarifa) setTarifa((t) => t || d.tarifa.replace(".", ","));
        if (d.embalagem) setEmbalagem((e) => (e === "BIG BAG" || !e ? d.embalagem : e));
      })
      .catch(() => { if (vivo) setSugestao(null); });
    return () => { vivo = false; };
  }, [agendamentoId]);

  function carregarNotas() {
    setCarregandoNotas(true);
    api.fiscalListarNotas()
      .then((d) => setNotas(d.notas || []))
      .catch(() => {})
      .finally(() => setCarregandoNotas(false));
  }

  useEffect(() => {
    if (origemNota === "recebida" && !notas.length && !carregandoNotas) carregarNotas();
  }, [origemNota]); // eslint-disable-line react-hooks/exhaustive-deps

  // Trocar de origem zera o espelho: ele foi montado com a nota anterior.
  function trocarOrigem(id) {
    setOrigemNota(id);
    setEspelho(null);
    setResultado(null);
    setErro("");
  }

  // A nota so esta pronta pra conferencia quando a origem escolhida tem o
  // que precisa. Sem isso o botao ficava habilitado e o erro so aparecia
  // depois da viagem ao servidor.
  const notaPronta =
    origemNota === "xml" ? !!arquivo
      : origemNota === "recebida" ? chaveNfe.replace(/\D/g, "").length === 44
      : Boolean(abrirChave(manual.chave) && manual.destinatario_doc && manual.produto
                && manual.peso_kg && manual.valor_nota && manual.modalidade_frete);

  // Tudo que ainda impede o "Conferir", de uma vez. Antes o botao ficava
  // apagado e a tela so citava o agendamento - quem escolhia a nota e
  // preenchia so ela via o botao morto sem saber por que.
  const faltando = [
    !agendamentoId && "o agendamento",
    !notaPronta && (
      origemNota === "xml" ? "o arquivo XML"
        : origemNota === "recebida" ? "a nota (ou a chave de 44 dígitos)"
        : "os dados da nota"
    ),
    !tarifa && "a tarifa por tonelada",
  ].filter(Boolean);

  const campos = (recentes) => ({
    origem_nota: origemNota,
    chave_nfe: origemNota === "recebida" ? chaveNfe : "",
    nota_manual: origemNota === "manual" ? JSON.stringify(manual) : "",
    agendamento_id: agendamentoId,
    tarifa_por_tonelada: String(tarifa).replace(",", "."),
    aliquota_icms: String(aliquota).replace(",", "."),
    km: String(km).replace(",", "."),
    forma_pagamento: formaPagamento,
    embalagem,
    especie_id: especieId,
    ...escolhas,
    ...(recentes || {}),
  });

  async function handleConferir(recentes) {
    if (!notaPronta) {
      setErro(
        origemNota === "xml" ? "Envie o XML da NF-e primeiro."
          : origemNota === "recebida" ? "Escolha a nota ou cole a chave de acesso."
          : "Preencha a chave, o destinatário, o produto, o peso, o valor e a modalidade do frete."
      );
      return;
    }
    setOcupado(true);
    setErro("");
    setResultado(null);
    try {
      const dados = await api.fiscalEspelho(arquivo, { ...campos(recentes), buscar_partes: true });
      setEspelho(dados);
      if (dados.especie?.especie_id && !especieId) setEspecieId(String(dados.especie.especie_id));
      /* Traz para os campos o que foi procurado no Bsoft. Antes isso ficava so
         no placeholder cinza: a tela parecia vazia e ninguem via a placa que o
         sistema usou. O que voce ja tiver digitado nao e sobrescrito. */
      const procurou = dados.veiculos?.procurou;
      if (procurou) {
        setEscolhas((x) => ({
          ...x,
          placa_cavalo: x.placa_cavalo || formatarPlaca(procurou.veiculo_id || ""),
          placa_carreta1: x.placa_carreta1 || formatarPlaca(procurou.carreta_id || ""),
          placa_carreta2: x.placa_carreta2 || formatarPlaca(procurou.semireboque_id || ""),
          motorista_cpf: x.motorista_cpf || formatarCpf(procurou.motorista_cpf || ""),
        }));
      }
    } catch (err) {
      setErro(err.message);
    } finally {
      setOcupado(false);
    }
  }

  async function handleEmitir() {
    setOcupado(true);
    setErro("");
    setResultado(null);
    try {
      setResultado(await api.fiscalEmitirConhecimento(arquivo, {
        ...campos(),
        confirmar_emissao_real: definitivo ? "true" : "",
      }));
    } catch (err) {
      setErro(err.message);
    } finally {
      setOcupado(false);
    }
  }

  const e = espelho || {};
  const p = espelho?.payload || {};
  const merc = p.mercadorias?.[0] || {};
  const pronto = espelho && !espelho.pendencias?.length;

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 15 }}>Emitir CT-e</strong>
          <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 4 }}>
            Mesmas seções da tela do Bsoft, preenchidas a partir da NF-e.
          </div>
        </div>
        <button className="btn-secondary" onClick={() => setAberto((v) => !v)}>
          {aberto ? "Fechar" : "Abrir"}
        </button>
      </div>

      {aberto && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Secao titulo="Dados da emissão">
            <div className="field-grid">
              <div className="field">
                <label>Agendamento</label>
                <select value={agendamentoId} onChange={(e) => setAgendamentoId(e.target.value)}>
                  <option value="">Selecione</option>
                  {agendamentos.map((a) => (
                    <option key={a.id} value={a.id}>
                      #{a.id} · {a.data_agendada || a.loading_date} · {a.driver_name || "sem motorista"} · {a.plate_cavalo}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Tarifa por tonelada</label>
                <input value={tarifa} onChange={(e) => setTarifa(e.target.value)} placeholder="300,00" />
                {sugestao?.cotacao && (
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>
                    Cotação de {sugestao.cotacao.data} para {sugestao.cotacao.destino}
                    {sugestao.cotacao.cliente ? ` (${sugestao.cotacao.cliente})` : ""}: R$ {sugestao.tarifa}/t
                  </span>
                )}
                {sugestao && !sugestao.cotacao && sugestao.destino && (
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>
                    Sem cotação registrada para {sugestao.destino}.
                  </span>
                )}
              </div>
              <div className="field">
                <label>Alíquota de ICMS (%)</label>
                <input value={aliquota} onChange={(e) => setAliquota(e.target.value)} placeholder="12" />
              </div>
              <div className="field">
                <label>Km do trecho</label>
                <input value={km} onChange={(e) => setKm(e.target.value)} placeholder="850" />
              </div>
              <div className="field">
                <label>Espécie da carga</label>
                <select value={especieId} onChange={(e) => setEspecieId(e.target.value)}>
                  <option value="">Pela embalagem do pedido</option>
                  {ESPECIES.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Embalagem do pedido</label>
                <select value={embalagem} onChange={(e) => setEmbalagem(e.target.value)}>
                  {EMBALAGENS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </div>
            </div>
          </Secao>

          <Secao titulo="De onde vem a nota">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {ORIGENS.map((op) => (
                <button
                  key={op.id}
                  type="button"
                  className={origemNota === op.id ? "btn-primary" : "btn-secondary"}
                  onClick={() => trocarOrigem(op.id)}
                  title={op.dica}
                  style={{ flex: "1 1 160px", flexDirection: "column", lineHeight: 1.3 }}
                >
                  <div>{op.rotulo}</div>
                  <div style={{ fontSize: 10.5, opacity: 0.75, fontWeight: 400 }}>{op.dica}</div>
                </button>
              ))}
            </div>

            {origemNota === "xml" && (
              <label className="btn-secondary" style={{ cursor: "pointer", alignSelf: "flex-start" }}>
                {arquivo ? "XML: " + arquivo.name : "Escolher o arquivo XML"}
                <input
                  type="file"
                  accept=".xml"
                  onChange={(e) => { setArquivo(e.target.files?.[0] || null); setEspelho(null); }}
                  style={{ display: "none" }}
                />
              </label>
            )}

            {origemNota === "recebida" && (
              <NotasRecebidas
                notas={notas}
                carregando={carregandoNotas}
                chave={chaveNfe}
                aoEscolher={(valor) => {
                  setChaveNfe(valor);
                  setEspelho(null);
                  // A nota casada traz o agendamento junto. O que ja foi
                  // escolhido na tela nao e sobrescrito.
                  const nota = notas.find((n) => n.chave === valor);
                  if (nota?.agendamento_id && !agendamentoId) setAgendamentoId(String(nota.agendamento_id));
                }}
                aoRecarregar={carregarNotas}
              />
            )}

            {origemNota === "manual" && (
              <NotaManual
                valores={manual}
                aoMudar={(campo, valor) => { setManual((m) => ({ ...m, [campo]: valor })); setEspelho(null); }}
              />
            )}

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <button
                className="btn-primary"
                disabled={ocupado || faltando.length > 0}
                onClick={handleConferir}
              >
                {ocupado ? "Processando..." : "Conferir"}
              </button>
              {faltando.length > 0 && (
                <span style={{ fontSize: 12, color: "var(--muted)" }}>
                  Falta informar {faltando.length === 1 ? faltando[0]
                    : faltando.slice(0, -1).join(", ") + " e " + faltando[faltando.length - 1]}.
                </span>
              )}
            </div>
          </Secao>

          {erro && <div className="inline-alert warning">{erro}</div>}

          {resultado && (
            <div className="inline-alert info">
              {resultado.rascunho ? "Rascunho criado" : "CT-e emitido"} — operação #{resultado.operacao?.id},
              {" "}CT-e {resultado.operacao?.cod_conhecimento_bsoft || "—"}. Confira no Bsoft.
            </div>
          )}

          {e.pendencias?.length > 0 && (
            <div className="inline-alert warning">
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <strong>Falta resolver antes de emitir:</strong>
                {e.pendencias.map((item, i) => <span key={i}>• {item}</span>)}
              </div>
            </div>
          )}

          {/* Avisos nao bloqueiam a emissao: sao coisas certas que so
              merecem um olhar antes de mandar. */}
          {e.avisos?.length > 0 && (
            <div className="inline-alert info">
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <strong>Confira:</strong>
                {e.avisos.map((item, i) => <span key={i}>• {item}</span>)}
              </div>
            </div>
          )}

          {espelho && !e.pendencias?.length && (
            <div className="inline-alert info">Tudo conferido. Pode gerar.</div>
          )}

              <Secao titulo="Identificação">
                <Linha>
                  <Campo rotulo="Modelo" valor="57" />
                  <Campo rotulo="Série" valor="1" />
                  <Campo rotulo="Tipo do CT-e" valor="Normal" />
                  <Campo rotulo="Tipo do serviço" valor="Normal" />
                  <Campo rotulo="Modal" valor="Rodoviário" />
                  <Campo rotulo="Emissão" valor={p.dtEmissao} />
                </Linha>
              </Secao>

              <Secao titulo="Prestação">
                <Linha>
                  <Campo rotulo="CFOP" valor={e.cfop} largura={2} />
                  <Campo rotulo="Origem" valor={`${e.municipio_origem} - ${e.uf_origem} (${e.ibge_origem})`} largura={3} />
                  <Campo rotulo="Destino" valor={`${e.municipio_destino} - ${e.uf_destino} (${e.ibge_destino})`} largura={3} />
                </Linha>
              </Secao>

              <Secao titulo="Participantes">
                <Linha>
                  <Campo rotulo="Remetente" valor={e.remetente_nome} largura={3} />
                  <Campo rotulo="CNPJ/CPF" valor={e.remetente_doc} />
                  <Campo rotulo="Cadastro" valor={e.partes?.remetente?.pessoa_id} />
                </Linha>
                <Linha>
                  <Campo rotulo="Destinatário" valor={e.destinatario_nome} largura={3} />
                  <Campo rotulo="CNPJ/CPF" valor={e.destinatario_doc} />
                  <Campo rotulo="Cadastro" valor={e.partes?.destinatario?.pessoa_id} />
                </Linha>
                {(e.partes?.remetente?.enderecos?.length > 1 || e.partes?.destinatario?.enderecos?.length > 1) && (
                  <Linha>
                    {e.partes?.remetente?.enderecos?.length > 1 && (
                      <Escolher
                        rotulo="Endereço do remetente"
                        valor={escolhas.endereco_remetente_id || e.partes.remetente.endereco_id}
                        opcoes={e.partes.remetente.enderecos}
                        aoMudar={(v) => {
                          const novas = { ...escolhas, endereco_remetente_id: v };
                          setEscolhas(novas);
                          handleConferir(novas);
                        }}
                      />
                    )}
                    {e.partes?.destinatario?.enderecos?.length > 1 && (
                      <Escolher
                        rotulo="Endereço do destinatário"
                        valor={escolhas.endereco_destinatario_id || e.partes.destinatario.endereco_id}
                        opcoes={e.partes.destinatario.enderecos}
                        aoMudar={(v) => {
                          const novas = { ...escolhas, endereco_destinatario_id: v };
                          setEscolhas(novas);
                          handleConferir(novas);
                        }}
                      />
                    )}
                  </Linha>
                )}
                <Linha>
                  <Campo rotulo="Tomador do serviço" valor={e.tomador === "destinatario" ? e.destinatario_nome : e.remetente_nome} largura={3} />
                  <Campo rotulo="Paga o frete" valor={p.pagamentoFrete === "D" ? "Destinatário" : p.pagamentoFrete === "R" ? "Remetente" : "—"} />
                  <Campo rotulo="Km" valor={p.km} />
                </Linha>
              </Secao>

              <Secao titulo="Carga">
                <Linha>
                  <Campo rotulo="Produto predominante" valor={e.produto_predominante} largura={4} />
                  <Campo rotulo="Espécie" valor={e.especie?.nome} largura={2} />
                </Linha>
                <Linha>
                  <Campo rotulo="Peso bruto" valor={`${e.peso_kg} kg`} />
                  <Campo rotulo="Quantidade" valor={e.quantidade} />
                  <Campo rotulo="Valor da mercadoria" valor={formatarValor(e.valor_mercadoria)} />
                  <Campo rotulo="Natureza da carga" valor={merc.naturezaCarga === "4" ? "Fertilizantes" : merc.naturezaCarga} />
                </Linha>
              </Secao>

              <Secao titulo="Documentos originários">
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ textAlign: "left", color: "var(--muted)" }}>
                        <th style={{ padding: "4px 8px 6px 0" }}>NF-e</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>Série</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>Emissão</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>CFOP</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>Valor</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>BC ICMS</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>ICMS</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>BC ST</th>
                        <th style={{ padding: "4px 8px 6px 0" }}>ST</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr style={{ fontVariantNumeric: "tabular-nums" }}>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.notaFiscal}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.serieNotaFiscal}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.dtFiscal}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{merc.nCFOP}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.valor)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vBC)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vICMS)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vBCST)}</td>
                        <td style={{ padding: "4px 8px 4px 0" }}>{formatarValor(merc.vST)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--muted)", wordBreak: "break-all" }}>
                  Chave: {merc.chaveNFe}
                </div>
              </Secao>

              <Secao titulo="Valores da prestação">
                <Linha>
                  <Campo rotulo="Tarifa peso" valor={formatarValor(p.tarifaDigitada)} />
                  <Campo rotulo="Frete valor" valor={formatarValor(p.valorFrete)} />
                  <Campo rotulo="Total do serviço" valor={formatarValor(p.totalServico)} />
                  <Campo rotulo="A receber" valor={formatarValor(p.totalPrestacao)} />
                </Linha>
              </Secao>

              <Secao titulo="Imposto">
                <Linha>
                  <Campo rotulo="Situação tributária" valor={p.CST === "000" ? "00 - Tributação normal" : p.CST} largura={2} />
                  <Campo rotulo="Base de cálculo" valor={formatarValor(p.baseCalculo)} />
                  <Campo rotulo="Alíquota" valor={p.aliquota ? `${p.aliquota},00%` : "—"} />
                  <Campo rotulo="Valor do ICMS" valor={formatarValor(p.valorICMS)} />
                </Linha>
              </Secao>

              <Secao titulo="Seguro">
                <Linha>
                  <Campo rotulo="Seguradora" valor="CHUBB SEGUROS BRASIL S.A." largura={3} />
                  <Campo rotulo="Apólice" valor={p.numeroApolice} />
                  <Campo rotulo="Responsável" valor="Emitente" />
                </Linha>
              </Secao>

              <Secao titulo="Veículo e motorista">
                <Linha>
                  {/* O que você escolheu na lupa vale mais do que o resultado
                      da última busca automática: antes o topo continuava
                      dizendo "não encontrado" mesmo com o motorista escolhido. */}
                  <Campo
                    rotulo="Motorista"
                    valor={
                      escolhas.motorista_nome
                        ? `${escolhas.motorista_nome}${escolhas.motorista_cpf ? ` · ${escolhas.motorista_cpf}` : ""}`
                        : e.veiculos?.motorista_id
                          ? `cadastro ${e.veiculos.motorista_id}`
                          : "não encontrado"
                    }
                  />
                  <Campo rotulo="Cavalo" valor={e.veiculos?.veiculo_id ? `cadastro ${e.veiculos.veiculo_id}` : "não encontrado"} />
                  <Campo rotulo="Carreta" valor={e.veiculos?.carreta_id ? `cadastro ${e.veiculos.carreta_id}` : "—"} />
                  <Campo rotulo="Segunda carreta" valor={e.veiculos?.semireboque_id ? `cadastro ${e.veiculos.semireboque_id}` : "—"} />
                </Linha>
                {e.veiculos?.procurou && (
                  <>
                    <div style={{ fontSize: 11.5, color: "var(--muted)" }}>
                      Procurei por: CPF {e.veiculos.procurou.motorista_cpf || "(vazio)"}, placas{" "}
                      {[e.veiculos.procurou.veiculo_id, e.veiculos.procurou.carreta_id, e.veiculos.procurou.semireboque_id]
                        .filter(Boolean).join(", ") || "(nenhuma)"}. Corrija abaixo se estiver diferente do cadastro do Bsoft.
                    </div>
                    {Object.keys(e.veiculos.placas_do_motorista || {}).length > 0 && (
                      <div className="inline-alert info" style={{ fontSize: 12 }}>
                        Placas puxadas do cadastro do motorista no Bsoft:{" "}
                        {Object.values(e.veiculos.placas_do_motorista).join(", ")}.
                      </div>
                    )}
                    <Linha>
                      <Corrigir
                        rotulo="CPF do motorista"
                        valor={escolhas.motorista_cpf}
                        placeholder={e.veiculos.procurou.motorista_cpf || "000.000.000-00"}
                        formatar={formatarCpf}
                        aoMudar={(v) => setEscolhas((x) => ({ ...x, motorista_cpf: v, motorista_id: "" }))}
                      />
                      <BuscaComLupa
                        rotulo="Ou procure o motorista pelo nome"
                        placeholder="nome do motorista"
                        procurar={api.fiscalProcurarMotoristas}
                        rotular={(r) => `${r.nome}${r.cpf ? " · " + r.cpf : ""}`}
                        escolhido={escolhas.motorista_nome}
                        /* Traz o CPF junto para o campo ao lado: quem escolheu
                           pelo nome quer conferir de quem se trata. O envio
                           continua usando o motorista_id — o backend so cai no
                           CPF quando nao ha id (fiscal.py, "if motorista_id"). */
                        aoEscolher={(r) => {
                          const novas = {
                            ...escolhas, motorista_id: r.id, motorista_nome: r.nome,
                            motorista_cpf: formatarCpf(r.cpf || ""),
                          };
                          setEscolhas(novas);
                          handleConferir(novas);
                        }}
                      />
                      <Corrigir
                        rotulo="Placa do cavalo"
                        valor={escolhas.placa_cavalo}
                        placeholder={e.veiculos.procurou.veiculo_id || "ABC1D23"}
                        formatar={formatarPlaca}
                        aoMudar={(v) => setEscolhas((x) => ({ ...x, placa_cavalo: v }))}
                      />
                      {/* O endpoint de busca de veiculo ja existia no backend e
                          no cliente, mas a tela nunca chamou. Serve para quando
                          a placa do agendamento nao bate com a do cadastro. */}
                      <BuscaComLupa
                        rotulo="Ou procure a placa"
                        placeholder="parte da placa"
                        procurar={api.fiscalProcurarVeiculos}
                        rotular={(r) => [r.placa, r.categoria, r.motorista].filter(Boolean).join(" · ")}
                        escolhido={escolhas.placa_cavalo_nome}
                        aoEscolher={(r) => setEscolhas((x) => ({
                          ...x, placa_cavalo: formatarPlaca(r.placa || ""), placa_cavalo_nome: r.placa,
                        }))}
                      />
                      <Corrigir
                        rotulo="Placa da carreta"
                        valor={escolhas.placa_carreta1}
                        placeholder={e.veiculos.procurou.carreta_id || "ABC1D23"}
                        formatar={formatarPlaca}
                        aoMudar={(v) => setEscolhas((x) => ({ ...x, placa_carreta1: v }))}
                      />
                      <Corrigir
                        rotulo="Segunda carreta"
                        valor={escolhas.placa_carreta2}
                        placeholder={e.veiculos.procurou.semireboque_id || "ABC1D23"}
                        formatar={formatarPlaca}
                        aoMudar={(v) => setEscolhas((x) => ({ ...x, placa_carreta2: v }))}
                      />
                    </Linha>
                    <div>
                      <button className="btn-secondary" disabled={ocupado} onClick={handleConferir}>
                        Buscar de novo
                      </button>
                    </div>
                  </>
                )}
              </Secao>

              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5 }}>
                  <input type="checkbox" checked={definitivo} onChange={(e) => setDefinitivo(e.target.checked)} />
                  Emitir definitivo (não rascunho)
                </label>
                <button className="btn-primary" disabled={ocupado || !pronto} onClick={handleEmitir}>
                  {definitivo ? "Emitir CT-e no Bsoft" : "Gerar rascunho no Bsoft"}
                </button>
                <details style={{ marginLeft: "auto" }}>
                  <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--muted)" }}>Ver JSON enviado</summary>
                  <pre className="card" style={{ fontSize: 11, marginTop: 8, overflow: "auto", maxHeight: 300 }}>
                    {JSON.stringify(p, null, 2)}
                  </pre>
                </details>
              </div>
        </div>
      )}
    </div>
  );
}

export default function DocumentosFiscaisPage() {
  const [dias, setDias] = useState(30);
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");

  async function carregar(periodo) {
    setCarregando(true);
    setErro("");
    try {
      setDados(await api.bsoftDocumentosFiscais(periodo));
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    carregar(dias);
  }, [dias]);

  const documentos = dados?.documentos || [];
  const termo = busca.trim().toLowerCase();
  const filtrados = termo
    ? documentos.filter((d) =>
        [d.cte_numero, d.destinatario, d.cliente, d.motorista, d.veiculo, d.ciot, d.chave_acesso]
          .some((campo) => String(campo || "").toLowerCase().includes(termo))
      )
    : documentos;

  const semCiot = documentos.filter((d) => !d.ciot).length;

  return (
    <div className="ops-page">
      <div className="dashboard-header">
        <div>
          <h2>Documentos fiscais emitidos</h2>
          <p>CT-e e contrato de frete (com CIOT) vindos do Bsoft — somente leitura.</p>
        </div>
      </div>

      <EmitirCte />

      <OperacoesRecentes />

      <div className="card" style={{ display: "flex", gap: 14, alignItems: "end", flexWrap: "wrap" }}>
        <div className="field" style={{ maxWidth: 200 }}>
          <label>Período</label>
          <select value={dias} onChange={(e) => setDias(Number(e.target.value))}>
            {PERIODOS.map((p) => (
              <option key={p.dias} value={p.dias}>Últimos {p.label}</option>
            ))}
          </select>
        </div>
        <div className="field pedidos-busca-field">
          <label>Buscar</label>
          <div className="pedidos-busca-wrap">
            <Icon name="search" size={15} />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="CT-e, cliente, motorista, placa, CIOT ou chave"
            />
          </div>
        </div>
        <button className="btn-secondary" disabled={carregando} onClick={() => carregar(dias)}>
          {carregando ? "Consultando..." : "Atualizar"}
        </button>
      </div>

      {erro && <div className="inline-alert error">{erro}</div>}
      {dados?.erros && Object.entries(dados.erros).map(([chave, msg]) => (
        <div className="inline-alert warning" key={chave}>Falha ao ler {chave}: {msg}</div>
      ))}

      {!carregando && documentos.length > 0 && semCiot > 0 && (
        <div className="inline-alert warning">
          <Icon name="shield" size={14} />
          {semCiot} CT-e sem contrato de frete/CIOT vinculado no período.
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {carregando ? (
          <div className="inline-alert info" style={{ margin: 16 }}><span className="status-dot" />Carregando...</div>
        ) : filtrados.length === 0 ? (
          <div className="inline-alert warning" style={{ margin: 16 }}>Nenhum documento no período.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>CT-e</th>
                  <th>Emissão</th>
                  <th>Destinatário</th>
                  <th>Motorista</th>
                  <th>Placa</th>
                  <th>Valor</th>
                  <th>CIOT</th>
                  <th>Agendamento</th>
                  <th>Chave de acesso</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((d) => (
                  <tr key={d.cte_id}>
                    <td><strong>{d.cte_numero}</strong></td>
                    <td>{formatarDataHora(d.emitido_em)}</td>
                    <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.destinatario}>
                      {d.destinatario || d.cliente || "-"}
                    </td>
                    <td style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.motorista}>
                      {d.motorista || "-"}
                    </td>
                    <td>{d.veiculo || "-"}{d.carreta ? ` / ${d.carreta}` : ""}</td>
                    <td>{formatarValor(d.valor)}</td>
                    <td>
                      {d.ciot
                        ? <span title={`Operadora: ${d.operadora || "-"} · Contrato ${d.contrato_numero || "-"}`}>{d.ciot}</span>
                        : <span style={{ color: "var(--warning)" }}>sem CIOT</span>}
                    </td>
                    <td>
                      {d.agendamento_id
                        ? <span title={d.agendamento_status || ""}>#{d.agendamento_id}</span>
                        : <span style={{ color: "var(--muted-soft)" }}>—</span>}
                    </td>
                    <td style={{ fontSize: 10.5, fontFamily: "monospace" }}>{d.chave_acesso || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
