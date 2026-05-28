"use client";

import { useState, useEffect, useRef } from "react";
import { runAnalysis, getStatus, getReport, getReadme, getSignals, type RunPayload, type HonestyMode } from "../lib/api";
import { getAccessToken, clearTokens } from "../lib/auth";
import LoginForm from "./LoginForm";
import ResultsPanel from "./ResultsPanel";

type Stage = "idle" | "running" | "done" | "error";

const HONESTY_MODES: { value: HonestyMode; label: string }[] = [
  { value: "authentic", label: "Authentic" },
  { value: "polished", label: "Polished" },
  { value: "recruiter", label: "Recruiter" },
  { value: "playful", label: "Playful" },
  { value: "technical", label: "Technical" },
  { value: "brutally_honest", label: "Brutally Honest" },
];

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued — waiting for worker…",
  ingesting: "Fetching GitHub data…",
  analyzing: "Computing signals…",
  completed: "Done",
};

export default function AnalysisForm() {
  const [authed, setAuthed] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [username, setUsername] = useState("");
  const [honestyMode, setHonestyMode] = useState<HonestyMode>("authentic");
  const [stage, setStage] = useState<Stage>("idle");
  const [statusText, setStatusText] = useState("");
  const [report, setReport] = useState<object | null>(null);
  const [readme, setReadme] = useState<object | null>(null);
  const [signals, setSignals] = useState<object[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setAuthed(!!getAccessToken());
  }, []);

  function logout() {
    clearTokens();
    setAuthed(false);
  }

  async function submit() {
    const name = username.trim();
    if (!name || stage === "running") return;

    setStage("running");
    setReport(null);
    setReadme(null);
    setSignals(null);
    setError("");
    setStatusText("queued");
    setShowLogin(false);

    try {
      const payload: RunPayload = {
        username: name,
        scope: "public",
        honesty_mode: honestyMode,
        output_targets: ["readme", "report"],
        include_private: false,
      };
      const { analysis_id } = await runAnalysis(payload);
      localStorage.setItem("analysis_id", analysis_id);

      let delay = 700;
      while (true) {
        await new Promise<void>((r) => setTimeout(r, delay));
        const { status } = await getStatus(analysis_id);
        setStatusText(status);
        if (status === "completed") break;
        if (status === "failed_permanent" || status === "failed") {
          throw new Error(`Analysis ${status}`);
        }
        delay = Math.min(delay * 1.5, 3500);
      }

      const [reportData, readmeData, signalsData] = await Promise.all([
        getReport(analysis_id),
        getReadme(analysis_id),
        getSignals(analysis_id),
      ]);
      setReport(reportData.report);
      setReadme({ markdown: readmeData.markdown, sections: readmeData.sections });
      setSignals(signalsData.signals ?? []);
      setStage("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setStage("error");
    }
  }

  return (
    <div>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>Analyze a GitHub Profile</h2>
          <div style={{ fontSize: 13, color: "#888", textAlign: "right" }}>
            {authed ? (
              <button onClick={logout} style={{ fontSize: 12, padding: "4px 10px", background: "none", border: "1px solid #ccc", color: "#666" }}>
                Log out
              </button>
            ) : (
              <button
                onClick={() => setShowLogin((v) => !v)}
                style={{ fontSize: 12, padding: "4px 10px", background: "none", border: "none", color: "var(--accent)", cursor: "pointer" }}
              >
                Sign in to save history
              </button>
            )}
          </div>
        </div>

        <div className="row">
          <input
            placeholder="GitHub username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            disabled={stage === "running"}
            style={{ flexGrow: 1 }}
          />
          <select
            value={honestyMode}
            onChange={(e) => setHonestyMode(e.target.value as HonestyMode)}
            disabled={stage === "running"}
          >
            {HONESTY_MODES.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <button onClick={submit} disabled={stage === "running"}>
            {stage === "running" ? "Analyzing…" : "Analyze"}
          </button>
        </div>

        {stage === "running" && (
          <p style={{ marginTop: 12, color: "var(--accent)", fontSize: 14 }}>
            {STATUS_LABELS[statusText] ?? statusText}
          </p>
        )}
        {stage === "error" && (
          <p style={{ marginTop: 12, color: "#c0392b", fontSize: 14 }}>{error}</p>
        )}
      </div>

      {showLogin && !authed && (
        <LoginForm onSuccess={() => { setAuthed(true); setShowLogin(false); }} />
      )}

      {stage === "done" && report && readme && (
        <ResultsPanel
          report={report as Parameters<typeof ResultsPanel>[0]["report"]}
          readme={readme as Parameters<typeof ResultsPanel>[0]["readme"]}
          signals={(signals ?? []) as Parameters<typeof ResultsPanel>[0]["signals"]}
        />
      )}
    </div>
  );
}
