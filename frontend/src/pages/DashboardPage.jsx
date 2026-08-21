import { useEffect, useState } from "react";
import * as api from "../api/client";
import Icon from "../components/Icon";

function formatTon(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

export default function DashboardPage() {
  const [resumo, setResumo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.obterResumoDashboard()
      .then(setResumo)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="ops-page"><div className="inline-alert info"><span className="status-dot" />Carregando dashboard...</div></div>;
  }
  if (error || !resumo) {
    return <div className="ops-page"><div className="inline-alert error">{error || "Não foi possível carregar o dashboard."}</div></div>;
  }

  const maiorDia = Math.max(1, ...resumo.semana.dias.map((d) => d.toneladas));
  const kpis = [
    ["Toneladas na semana", `${formatTon(resumo.semana.toneladas_total)} t`, "chart"],
    ["Agendamentos na semana", resumo.semana.agendamentos_total, "calendar"],
    ["Saldo de pedidos", `${formatTon(resumo.pedidos.saldo_total)} t`, "contract"],
    ["Agendamentos em aberto", resumo.agendamentos_em_aberto, "clipboard"],
  ];

  return (
    <div className="ops-page">
      <div className="dashboard-header">
        <div>
          <h2>Visão geral de carregamentos</h2>
          <p>Semana de {resumo.semana.inicio} a {resumo.semana.fim}</p>
        </div>
      </div>

      <div className="metric-grid">
        {kpis.map(([label, value, icon]) => (
          <div className="metric-card" key={label}>
            <span className="metric-icon"><Icon name={icon} /></span>
            <div><small>{label}</small><strong>{value}</strong></div>
          </div>
        ))}
      </div>

      <section className="card dashboard-week-card">
        <div className="section-heading">
          <div>
            <span className="section-index"><Icon name="route" size={16} /></span>
            <div><h2>Programação de carregamentos da semana</h2><p>Toneladas agendadas por dia, segunda a sábado.</p></div>
          </div>
        </div>
        <div className="dashboard-week-list">
          {resumo.semana.dias.map((d) => (
            <div className="dashboard-week-row" key={d.data}>
              <div className="dashboard-week-day">
                <strong>{d.dia}</strong>
                <span>{d.data}</span>
              </div>
              <div className="dashboard-week-bar-wrap">
                <div className="dashboard-week-bar" style={{ width: `${(d.toneladas / maiorDia) * 100}%` }} />
              </div>
              <div className="dashboard-week-values">
                <strong>{formatTon(d.toneladas)} t</strong>
                <span>{d.agendamentos} agend.</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
