export function formatCPF(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 11);
  let out = digits;
  if (digits.length > 9) out = digits.replace(/(\d{3})(\d{3})(\d{3})(\d{1,2})/, "$1.$2.$3-$4");
  else if (digits.length > 6) out = digits.replace(/(\d{3})(\d{3})(\d{1,3})/, "$1.$2.$3");
  else if (digits.length > 3) out = digits.replace(/(\d{3})(\d{1,3})/, "$1.$2");
  return out;
}

export function formatDateInput(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
  let out = digits;
  if (digits.length > 4) out = digits.replace(/(\d{2})(\d{2})(\d{1,4})/, "$1/$2/$3");
  else if (digits.length > 2) out = digits.replace(/(\d{2})(\d{1,2})/, "$1/$2");
  return out;
}
