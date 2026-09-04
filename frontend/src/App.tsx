import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { useAuth } from "./lib/auth";

export function App() {
  const { token } = useAuth();
  return token ? <Dashboard /> : <Login />;
}
