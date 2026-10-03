import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ContratoProvider } from "./context/ContratoContext";
import { ThemeProvider } from "./context/ThemeContext";
import AdminPage from "./pages/AdminPage";
import ConfiguracoesPage from "./pages/ConfiguracoesPage";
import AgendamentosPage from "./pages/AgendamentosPage";
import AnaliseFretesPage from "./pages/AnaliseFretesPage";
import BsoftPage from "./pages/BsoftPage";
import BuonnyPage from "./pages/BuonnyPage";
import CartaFretePage from "./pages/CartaFretePage";
import ClientesPage from "./pages/ClientesPage";
import ContratoPage from "./pages/ContratoPage";
import DashboardPage from "./pages/DashboardPage";
import DocumentosFiscaisPage from "./pages/DocumentosFiscaisPage";
import EmailsPage from "./pages/EmailsPage";
import LoginPage from "./pages/LoginPage";
import OrdemColetaPage from "./pages/OrdemColetaPage";
import PedidosPage from "./pages/PedidosPage";
import TrocarSenhaPage from "./pages/TrocarSenhaPage";
import WhatsAppPage from "./pages/WhatsAppPage";
import CaixaPage from "./pages/financeiro/CaixaPage";
import CarregamentosPage from "./pages/financeiro/CarregamentosPage";
import { AgenciamentosPage, DividasPage, FaturasPage, GastosPage, LucroBrutoPage, PagamentosPage, PrecificacaoPage } from "./pages/financeiro/PaginasFinanceiro";

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="app-loading"><span />Carregando ambiente...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="app-loading"><span />Carregando ambiente...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") return <Navigate to="/ordem-coleta" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route path="/" element={<Navigate to="/ordem-coleta" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/contrato" element={<ContratoPage />} />
        <Route path="/pedidos" element={<PedidosPage />} />
        <Route path="/ordem-coleta" element={<OrdemColetaPage />} />
        <Route path="/autorizacao-abastecimento" element={<CartaFretePage />} />
        <Route path="/carta-frete" element={<Navigate to="/autorizacao-abastecimento" replace />} />
        {/* Financeiro: quem ve cada aba sai da permissao por tela (o menu
            esconde e o backend recusa com 403); gravar segue so admin. */}
        <Route path="/financeiro/caixa" element={<CaixaPage />} />
        <Route path="/financeiro/carregamentos" element={<CarregamentosPage />} />
        <Route path="/financeiro/lucro-bruto" element={<LucroBrutoPage />} />
        <Route path="/financeiro/gastos" element={<GastosPage />} />
        <Route path="/financeiro/precificacao" element={<PrecificacaoPage />} />
        <Route path="/financeiro/pagamentos" element={<PagamentosPage />} />
        <Route path="/financeiro/faturas" element={<FaturasPage />} />
        <Route path="/financeiro/agenciamentos" element={<AgenciamentosPage />} />
        <Route path="/financeiro/comissoes" element={<Navigate to="/financeiro/agenciamentos" replace />} />
        <Route path="/financeiro/dividas" element={<DividasPage />} />
        {/* Enderecos das versoes anteriores. */}
        <Route path="/financeiro/resultado" element={<Navigate to="/financeiro/lucro-bruto" replace />} />
        <Route path="/financeiro/contas" element={<Navigate to="/financeiro/pagamentos" replace />} />
        <Route path="/agendamentos" element={<AgendamentosPage />} />
        <Route path="/analise-fretes" element={<AnaliseFretesPage />} />
        <Route path="/documentos-fiscais" element={<DocumentosFiscaisPage />} />
        <Route path="/clientes" element={<ClientesPage />} />
        <Route path="/emails" element={<EmailsPage />} />
        <Route path="/whatsapp" element={<WhatsAppPage />} />
        <Route path="/buonny" element={<BuonnyPage />} />
        <Route path="/bsoft" element={<BsoftPage />} />
        <Route path="/trocar-senha" element={<TrocarSenhaPage />} />
        <Route
          path="/configuracoes"
          element={
            <AdminRoute>
              <ConfiguracoesPage />
            </AdminRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <AdminPage />
            </AdminRoute>
          }
        />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ContratoProvider>
          <AppRoutes />
        </ContratoProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
