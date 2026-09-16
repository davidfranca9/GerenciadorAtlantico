// Numeros e datas do financeiro, no jeito brasileiro.

const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const DIAS_SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

export const FORMAS = [
  { valor: "PIX", rotulo: "Pix", icone: "pix" },
  { valor: "TRANSFERENCIA", rotulo: "Transferência", icone: "transfer" },
  { valor: "BOLETO", rotulo: "Boleto", icone: "barcode" },
  { valor: "DEBITO", rotulo: "Débito", icone: "card" },
  { valor: "CARTAO", rotulo: "Cartão", icone: "card" },
  { valor: "CHEQUE", rotulo: "Cheque", icone: "file" },
  { valor: "RENDIMENTO", rotulo: "Rendimento", icone: "trend" },
  { valor: "DINHEIRO", rotulo: "Dinheiro", icone: "coins" },
  { valor: "OUTRO", rotulo: "Outro", icone: "coins" },
];

export function formaInfo(valor) {
  return FORMAS.find((f) => f.valor === valor) || FORMAS[FORMAS.length - 1];
}

export function brl(valor, { sinal = false, centavos = true } = {}) {
  if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return "—";
  const numero = Number(valor);
  const texto = Math.abs(numero).toLocaleString("pt-BR", {
    minimumFractionDigits: centavos ? 2 : 0,
    maximumFractionDigits: centavos ? 2 : 0,
  });
  const prefixo = numero < 0 ? "−" : sinal && numero > 0 ? "+" : "";
  return `${prefixo}R$ ${texto}`;
}

// Pra caber numa celula de calendario: "32,2 mil", "4.418" (sem o R$).
export function brlCurto(valor) {
  const numero = Number(valor || 0);
  if (Math.abs(numero) >= 10000) {
    return `${(numero / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  }
  return numero.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

// "R$ 69.358,24" em pedacos, pra desenhar os centavos menores.
export function partesBrl(valor) {
  const numero = Number(valor || 0);
  const [inteiro, cents] = Math.abs(numero).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).split(",");
  return { negativo: numero < 0, inteiro, centavos: cents };
}

export function toneladas(valor, casas = 1) {
  if (valor === null || valor === undefined) return "—";
  return `${Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: casas })} t`;
}

export function numeroBr(texto) {
  // "1.234,56" -> 1234.56 · "9.000" -> 9000 · "1234.56" -> 1234.56 · "1234,5" -> 1234.5
  // Ponto so e decimal quando nao parece separador de milhar: antes "9.000"
  // (como o proprio campo mostrava) virava 9.
  const limpo = String(texto ?? "").replace(/[R$\s]/g, "");
  if (!limpo) return null;
  let normalizado = limpo;
  if (limpo.includes(",")) normalizado = limpo.replace(/\./g, "").replace(",", ".");
  else if (/^-?\d{1,3}(\.\d{3})+$/.test(limpo)) normalizado = limpo.replace(/\./g, "");
  const numero = Number(normalizado);
  return Number.isFinite(numero) ? numero : null;
}

// Campo de digitar: sem ponto de milhar ("9000", "614,21"), pra nao confundir.
export function valorParaCampo(valor) {
  if (valor === null || valor === undefined || valor === "") return "";
  return Number(valor).toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 2, useGrouping: false });
}

export function diasAte(iso, hoje = hojeIso()) {
  return Math.round((dataDe(iso) - dataDe(hoje)) / 86400000);
}

export function hojeIso() {
  const agora = new Date();
  return isoDe(agora);
}

export function isoDe(data) {
  const y = data.getFullYear();
  const m = String(data.getMonth() + 1).padStart(2, "0");
  const d = String(data.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function dataDe(iso) {
  const [y, m, d] = String(iso).split("-").map(Number);
  return new Date(y, m - 1, d || 1);
}

export function somarDias(iso, dias) {
  const data = dataDe(iso);
  data.setDate(data.getDate() + dias);
  return isoDe(data);
}

export function diaCurto(iso) {
  if (!iso) return "sem data";
  const data = dataDe(iso);
  return `${String(data.getDate()).padStart(2, "0")} ${MESES_CURTOS[data.getMonth()]}`;
}

export function diaBr(iso) {
  if (!iso) return "";
  const data = dataDe(iso);
  return `${String(data.getDate()).padStart(2, "0")}/${String(data.getMonth() + 1).padStart(2, "0")}/${data.getFullYear()}`;
}

export function diaPorExtenso(iso, hoje = hojeIso()) {
  const data = dataDe(iso);
  const base = `${data.getDate()} de ${MESES[data.getMonth()]}`;
  if (iso === hoje) return `Hoje, ${base}`;
  if (iso === somarDias(hoje, -1)) return `Ontem, ${base}`;
  const semana = DIAS_SEMANA[data.getDay()];
  return `${semana[0].toUpperCase()}${semana.slice(1)}, ${base}`;
}

export function competenciaDe(iso) {
  return String(iso).slice(0, 7);
}

export function nomeCompetencia(competencia) {
  const [ano, mes] = competencia.split("-").map(Number);
  const nome = MESES[mes - 1];
  return `${nome[0].toUpperCase()}${nome.slice(1)} de ${ano}`;
}

export function mudarCompetencia(competencia, delta) {
  const [ano, mes] = competencia.split("-").map(Number);
  const data = new Date(ano, mes - 1 + delta, 1);
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}`;
}

export function periodoDe(tipo, iso) {
  if (tipo === "semana") {
    const data = dataDe(iso);
    const segunda = new Date(data);
    segunda.setDate(data.getDate() - ((data.getDay() + 6) % 7));
    const domingo = new Date(segunda);
    domingo.setDate(segunda.getDate() + 6);
    return { inicio: isoDe(segunda), fim: isoDe(domingo) };
  }
  if (tipo === "mes") {
    const data = dataDe(iso);
    return { inicio: isoDe(new Date(data.getFullYear(), data.getMonth(), 1)), fim: isoDe(new Date(data.getFullYear(), data.getMonth() + 1, 0)) };
  }
  return { inicio: iso, fim: iso };
}

export function rotuloPeriodo(tipo, iso) {
  const { inicio, fim } = periodoDe(tipo, iso);
  if (tipo === "mes") return nomeCompetencia(competenciaDe(iso));
  if (tipo === "semana") return `${diaCurto(inicio)} – ${diaCurto(fim)}`;
  return diaPorExtenso(iso);
}
