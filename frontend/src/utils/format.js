export function formatCPF(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
  let out = digits;
  if (digits.length > 9) out = digits.replace(/(\d{3})(\d{3})(\d{3})(\d{1,2})/, "$1.$2.$3-$4");
  else if (digits.length > 6) out = digits.replace(/(\d{3})(\d{3})(\d{1,3})/, "$1.$2.$3");
  else if (digits.length > 3) out = digits.replace(/(\d{3})(\d{1,3})/, "$1.$2");
  return out;
}

export function formatCNPJ(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 14);
  let out = digits;
  if (digits.length > 12) out = digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{1,2})/, "$1.$2.$3/$4-$5");
  else if (digits.length > 8) out = digits.replace(/(\d{2})(\d{3})(\d{3})(\d{1,4})/, "$1.$2.$3/$4");
  else if (digits.length > 5) out = digits.replace(/(\d{2})(\d{3})(\d{1,3})/, "$1.$2.$3");
  else if (digits.length > 2) out = digits.replace(/(\d{2})(\d{1,3})/, "$1.$2");
  return out;
}

export function formatCEP(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
  if (digits.length > 5) return digits.replace(/(\d{5})(\d{1,3})/, "$1-$2");
  return digits;
}

export function formatDateInput(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
  let out = digits;
  if (digits.length > 4) out = digits.replace(/(\d{2})(\d{2})(\d{1,4})/, "$1/$2/$3");
  else if (digits.length > 2) out = digits.replace(/(\d{2})(\d{1,2})/, "$1/$2");
  return out;
}

export function formatMoney(value) {
  const digits = String(value || "").replace(/\D/g, "").replace(/^0+(?=\d)/, "").slice(0, 12);
  if (!digits) return "";
  const cents = digits.padStart(3, "0");
  const intPart = cents.slice(0, -2).replace(/^0+(?=\d)/, "");
  const decPart = cents.slice(-2);
  const withThousands = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${withThousands},${decPart}`;
}

export function formatPhone(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
  if (digits.length === 0) return "";
  if (digits.length <= 2) return `(${digits}`;
  const ddd = digits.slice(0, 2);
  const rest = digits.slice(2);
  let out = `(${ddd}) `;
  if (rest.length === 0) return out;
  const nono = rest[0];
  const restante = rest.slice(1);
  out += nono;
  if (restante.length === 0) return out;
  out += " ";
  if (restante.length <= 4) return out + restante;
  return out + `${restante.slice(0, 4)}-${restante.slice(4, 8)}`;
}

export function formatPlaca(value) {
  const clean = String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 7);
  if (clean.length > 3) return `${clean.slice(0, 3)}-${clean.slice(3)}`;
  return clean;
}

export function formatNome(value) {
  return String(value || "").toUpperCase();
}
