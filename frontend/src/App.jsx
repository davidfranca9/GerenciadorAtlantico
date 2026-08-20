import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ContratoProvider } from "./context/ContratoContext";
import { ThemeProvider } from "./context/ThemeContext";
import AdminPage from "./pages/AdminPage";
import AgendamentosPage from "./pages/AgendamentosPage";
import AnaliseFretesPage from "./pages/AnaliseFretesPage";
import BsoftPage from "./pages/BsoftPage";
import BuonnyPage from "./pages/BuonnyPage";
import CartaFretePage from "./pages/CartaFretePage";
import ClientesPage from "./pages/ClientesPage";
import ContratoPage from "./pages/ContratoPage";
import EmailsPage from "./pages/EmailsPage";
import LoginPage from "./pages/LoginPage";
import OrdemColetaPage from "./pages/OrdemColetaPage";
import TrocarSenhaPage from "./pages/TrocarSenhaPage";

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
        <Route path="/contrato" element={<ContratoPage />} />
        <Route path="/ordem-coleta" element={<OrdemColetaPage />} />
        <Route path="/carta-frete" element={<CartaFretePage />} />
        <Route path="/agendamentos" element={<AgendamentosPage />} />
        <Route path="/analise-fretes" element={<AnaliseFretesPage />} />
        <Route path="/clientes" element={<ClientesPage />} />
        <Route path="/emails" element={<EmailsPage />} />
        <Route path="/buonny" element={<BuonnyPage />} />
        <Route path="/bsoft" element={<BsoftPage />} />
        <Route path="/trocar-senha" element={<TrocarSenhaPage />} />
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
