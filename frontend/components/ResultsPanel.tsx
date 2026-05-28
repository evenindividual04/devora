"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type ArchetypeResult = {
  top_archetype: string;
  alternates: string[];
  confidence: number;
  limited_data?: boolean;
};

type Report = {
  summary: string;
  archetype: ArchetypeResult;
  standout_repos: string[];
  timeline: string[];
};

type ReadmeResult = {
  markdown: string;
  generator?: string;
};

type Signal = {
  name: string;
  value: number | string;
  confidence: number;
  timeframe: string;
};

interface Props {
  report: Report;
  readme: ReadmeResult;
  signals: Signal[];
}

function fmt(v: number | string): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return v;
}

// High-validity signals shown by default — ordered by informativeness
const PRIORITY_SIGNALS = [
  "primary_language",
  "activity_trajectory",
  "commits_per_week",
  "max_stars",
  "avg_churn_per_commit",
  "feature_ratio",
  "fix_ratio",
  "pr_authored_count",
  "pr_review_ratio",
  "authorship_dominance",
  "language_entropy",
  "months_active_last_year",
  "weekday_commit_ratio",
  "human_commit_ratio",
  "streak_months",
  "language_diversity",
  "recent_primary_language",
  "language_shifted",
];

function isVanityZero(signal: Signal): boolean {
  // Hide signals that are 0 and don't tell us anything useful
  const zeroVanity = new Set([
    "max_stars", "avg_stars", "ml_domain_bias", "infra_domain_bias",
    "tooling_domain_bias", "systems_domain_bias", "pr_review_ratio",
    "authorship_dominance", "backdated_commit_ratio",
  ]);
  return zeroVanity.has(signal.name) && signal.value === 0;
}

export default function ResultsPanel({ report, readme, signals }: Props) {
  const { archetype, summary, standout_repos, timeline } = report;
  const [signalsOpen, setSignalsOpen] = useState(false);
  const [showAllSignals, setShowAllSignals] = useState(false);

  // Curate: priority signals first, hide zero-value vanity
  const prioritySet = new Set(PRIORITY_SIGNALS);
  const prioritySignals = signals.filter(
    (s) => prioritySet.has(s.name) && !isVanityZero(s)
  ).sort((a, b) => PRIORITY_SIGNALS.indexOf(a.name) - PRIORITY_SIGNALS.indexOf(b.name));
  const otherSignals = signals.filter((s) => !prioritySet.has(s.name) && !isVanityZero(s));
  const displayedSignals = showAllSignals ? signals.filter((s) => !isVanityZero(s)) : prioritySignals;

  const generator = readme.generator;
  const isLLM = generator && generator !== "deterministic";

  return (
    <div>
      <div className="card" style={{ borderLeft: "4px solid var(--accent)" }}>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "#888" }}>
          Archetype
        </span>
        <h2 style={{ margin: "4px 0 2px" }}>{archetype.top_archetype}</h2>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "#666" }}>
          {(archetype.confidence * 100).toFixed(0)}% confidence
          {archetype.limited_data && (
            <span style={{ marginLeft: 8, color: "#999" }}>· limited data</span>
          )}
          {archetype.alternates.length > 0 && (
            <span style={{ marginLeft: 8 }}>· also: {archetype.alternates.join(", ")}</span>
          )}
        </p>
        <p style={{ margin: "0 0 10px" }}>{summary}</p>
        {standout_repos.length > 0 && (
          <p style={{ fontSize: 13, color: "#555", margin: "0 0 8px" }}>
            <strong>Standout repos:</strong>{" "}
            {standout_repos.map((r) => (
              <code key={r} style={{ marginRight: 8, background: "#f0f4f6", padding: "2px 6px", borderRadius: 4 }}>
                {r}
              </code>
            ))}
          </p>
        )}
        {timeline.length > 0 && (
          <ul style={{ margin: "8px 0 0", paddingLeft: 20, fontSize: 13, color: "#555" }}>
            {timeline.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        )}
      </div>

      {signals.length > 0 && (
        <div className="card">
          <button
            style={{ background: "none", border: "none", padding: 0, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontSize: 15, fontWeight: 600, color: "inherit" }}
            onClick={() => setSignalsOpen((o) => !o)}
          >
            <span>{signalsOpen ? "▾" : "▸"}</span>
            Signals ({prioritySignals.length} key · {signals.length} total)
          </button>

          {signalsOpen && (
            <>
              <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12, fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #d8e3e7" }}>
                    <th style={{ textAlign: "left", padding: "4px 8px 8px 0", color: "#888", fontWeight: 500 }}>Signal</th>
                    <th style={{ textAlign: "right", padding: "4px 8px 8px", color: "#888", fontWeight: 500 }}>Value</th>
                    <th style={{ textAlign: "right", padding: "4px 0 8px 8px", color: "#888", fontWeight: 500 }}>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedSignals.map((s) => (
                    <tr key={s.name} style={{ borderBottom: "1px solid #f0f4f6" }}>
                      <td style={{ padding: "6px 8px 6px 0", color: "#333" }}>
                        {s.name.replace(/_/g, " ")}
                      </td>
                      <td style={{ padding: "6px 8px", textAlign: "right", fontFamily: "monospace" }}>
                        {fmt(s.value)}
                      </td>
                      <td style={{ padding: "6px 0 6px 8px", textAlign: "right" }}>
                        <span style={{
                          display: "inline-block",
                          width: 40,
                          height: 6,
                          background: "#e8eef0",
                          borderRadius: 3,
                          position: "relative",
                          verticalAlign: "middle",
                          marginRight: 6,
                        }}>
                          <span style={{
                            display: "block",
                            width: `${(s.confidence * 100).toFixed(0)}%`,
                            height: "100%",
                            background: "var(--accent)",
                            borderRadius: 3,
                          }} />
                        </span>
                        {(s.confidence * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {otherSignals.length > 0 && (
                <button
                  style={{ marginTop: 8, background: "none", border: "none", color: "var(--accent)", cursor: "pointer", fontSize: 12, padding: 0 }}
                  onClick={() => setShowAllSignals((v) => !v)}
                >
                  {showAllSignals ? "Show fewer signals" : `Show all ${signals.filter(s => !isVanityZero(s)).length} signals`}
                </button>
              )}
            </>
          )}
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Generated README</h3>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {generator && (
              <span style={{ fontSize: 11, color: "#aaa" }}>
                {isLLM ? `via ${generator}` : "deterministic fallback"}
              </span>
            )}
            <button
              style={{ fontSize: 12, padding: "6px 12px" }}
              onClick={() => navigator.clipboard.writeText(readme.markdown)}
            >
              Copy markdown
            </button>
          </div>
        </div>
        <div style={{
          background: "#f4f8f9",
          border: "1px solid #d8e3e7",
          borderRadius: 8,
          padding: 20,
          fontSize: 14,
          lineHeight: 1.7,
          overflowX: "auto",
        }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h1 style={{ fontSize: 22, marginTop: 0, marginBottom: 12 }}>{children}</h1>,
              h2: ({ children }) => <h2 style={{ fontSize: 17, marginTop: 20, marginBottom: 8, borderBottom: "1px solid #d8e3e7", paddingBottom: 4 }}>{children}</h2>,
              h3: ({ children }) => <h3 style={{ fontSize: 15, marginTop: 16, marginBottom: 6 }}>{children}</h3>,
              p: ({ children }) => <p style={{ margin: "0 0 12px" }}>{children}</p>,
              code: ({ children }) => <code style={{ background: "#e8eef0", padding: "2px 5px", borderRadius: 3, fontSize: 12, fontFamily: "monospace" }}>{children}</code>,
              ul: ({ children }) => <ul style={{ paddingLeft: 20, margin: "0 0 12px" }}>{children}</ul>,
              li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
              em: ({ children }) => <em style={{ color: "#666" }}>{children}</em>,
              strong: ({ children }) => <strong>{children}</strong>,
            }}
          >
            {readme.markdown}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
