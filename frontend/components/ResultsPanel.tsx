"use client";

import { useState } from "react";

type ArchetypeResult = {
  top_archetype: string;
  alternates: string[];
  confidence: number;
};

type Report = {
  summary: string;
  archetype: ArchetypeResult;
  standout_repos: string[];
  timeline: string[];
};

type ReadmeResult = {
  markdown: string;
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

export default function ResultsPanel({ report, readme, signals }: Props) {
  const { archetype, summary, standout_repos, timeline } = report;
  const [signalsOpen, setSignalsOpen] = useState(false);

  return (
    <div>
      <div className="card" style={{ borderLeft: "4px solid var(--accent)" }}>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, color: "#888" }}>
          Archetype
        </span>
        <h2 style={{ margin: "4px 0 2px" }}>{archetype.top_archetype}</h2>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "#666" }}>
          {(archetype.confidence * 100).toFixed(0)}% confidence
          {archetype.alternates.length > 0 && ` · also: ${archetype.alternates.join(", ")}`}
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
            Signals ({signals.length})
          </button>

          {signalsOpen && (
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12, fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #d8e3e7" }}>
                  <th style={{ textAlign: "left", padding: "4px 8px 8px 0", color: "#888", fontWeight: 500 }}>Signal</th>
                  <th style={{ textAlign: "right", padding: "4px 8px 8px", color: "#888", fontWeight: 500 }}>Value</th>
                  <th style={{ textAlign: "right", padding: "4px 0 8px 8px", color: "#888", fontWeight: 500 }}>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => (
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
          )}
        </div>
      )}

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Generated README</h3>
          <button
            style={{ fontSize: 12, padding: "6px 12px" }}
            onClick={() => navigator.clipboard.writeText(readme.markdown)}
          >
            Copy markdown
          </button>
        </div>
        <pre style={{
          background: "#f4f8f9",
          border: "1px solid #d8e3e7",
          borderRadius: 8,
          padding: 16,
          fontSize: 13,
          lineHeight: 1.65,
          overflowX: "auto",
          margin: 0,
        }}>
          {readme.markdown}
        </pre>
      </div>
    </div>
  );
}
