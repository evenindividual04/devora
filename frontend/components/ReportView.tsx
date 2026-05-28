"use client";

import { useState } from "react";
import { getReport, getSignals } from "../lib/api";

export default function ReportView() {
  const [id, setId] = useState("");
  const [report, setReport] = useState<any>(null);
  const [signals, setSignals] = useState<any>(null);

  async function load() {
    setReport(await getReport(id));
    setSignals(await getSignals(id));
  }

  return (
    <div className="card">
      <h2>Report Explorer</h2>
      <div className="row">
        <input value={id} onChange={(e) => setId(e.target.value)} placeholder="analysis id" />
        <button onClick={load}>Load</button>
      </div>
      <h3>Report</h3>
      <pre>{JSON.stringify(report, null, 2)}</pre>
      <h3>Signals</h3>
      <pre>{JSON.stringify(signals, null, 2)}</pre>
    </div>
  );
}
