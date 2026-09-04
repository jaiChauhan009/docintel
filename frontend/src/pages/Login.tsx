import { useState, type FormEvent } from "react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export function Login() {
  const { setToken } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("demo@docintel.io");
  const [password, setPassword] = useState("demo-password-123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const fn = mode === "login" ? api.login : api.register;
      const { access_token } = await fn(email, password);
      setToken(access_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container" style={{ maxWidth: 420 }}>
      <h1>DocIntel</h1>
      <div className="card">
        <div className="row" style={{ marginBottom: 14 }}>
          <button className={mode === "login" ? "primary" : ""} onClick={() => setMode("login")}>
            Log in
          </button>
          <button className={mode === "register" ? "primary" : ""} onClick={() => setMode("register")}>
            Register
          </button>
        </div>
        <form onSubmit={submit}>
          <label>Email</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
          <div style={{ height: 10 }} />
          <label>Password</label>
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            minLength={8}
            required
          />
          <div style={{ height: 14 }} />
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "..." : mode === "login" ? "Log in" : "Create account"}
          </button>
          {error && <p className="error">{error}</p>}
        </form>
      </div>
    </div>
  );
}
