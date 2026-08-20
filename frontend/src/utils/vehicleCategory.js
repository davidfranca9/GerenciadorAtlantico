export const CATEGORIAS_TRATORAS = new Set([
  "CAVALO", "TRUCK", "CAVALO 4 EIXOS", "CAVALO TRUCADO 3 EIXOS", "BITRUCK", "TOCO", "3/4", "VAN", "AUTOMÓVEIS",
]);
export const CATEGORIAS_REBOCADAS = new Set(["SEMI-REBOQUE 1", "SEMI-REBOQUE 2", "CARRETA", "DOLLY"]);

export function ordenarVeiculosPorCategoria(veiculos) {
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
