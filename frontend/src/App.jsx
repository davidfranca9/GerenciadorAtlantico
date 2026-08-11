import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AgendamentosPage from "./pages/AgendamentosPage";
import AnaliseFretesPage from "./pages/AnaliseFretesPage";
import CartaFretePage from "./pages/CartaFretePage";
import LoginPage from "./pages/LoginPage";
import OrdemColetaPage from "./pages/OrdemColetaPage";

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ padding: 40 }}>Carregando...</div>;
  if (!user) return <Navigate to="/login" replace />;
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
        <Route path="/ordem-coleta" element={<OrdemColetaPage />} />
        <Route path="/carta-frete" element={<CartaFretePage />} />
        <Route path="/agendamentos" element={<AgendamentosPage />} />
        <Route path="/analise-fretes" element={<AnaliseFretesPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}
