"use client";

import { useState } from "react";
import { login, register } from "../lib/api";
import { setTokens } from "../lib/auth";

interface Props {
  onSuccess?: () => void;
}

export default function LoginForm({ onSuccess }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handle(action: "login" | "register") {
    if (!email || !password) return;
    setLoading(true);
    setError("");
    try {
      const data = action === "login" ? await login(email, password) : await register(email, password);
      setTokens(data.access_token, data.refresh_token);
      onSuccess?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Sign in to analyze</h2>
      <div className="row" style={{ flexDirection: "column", gap: 10 }}>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          type="email"
          disabled={loading}
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          type="password"
          disabled={loading}
          onKeyDown={(e) => e.key === "Enter" && handle("login")}
        />
        <div className="row" style={{ gap: 8 }}>
          <button onClick={() => handle("login")} disabled={loading} style={{ flexGrow: 1 }}>
            {loading ? "…" : "Log in"}
          </button>
          <button onClick={() => handle("register")} disabled={loading} style={{ flexGrow: 1 }}>
            {loading ? "…" : "Create account"}
          </button>
        </div>
      </div>
      {error && <p style={{ color: "#c0392b", fontSize: 13, marginTop: 10 }}>{error}</p>}
    </div>
  );
}
