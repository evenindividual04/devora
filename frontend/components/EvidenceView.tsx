"use client";

import { useState } from "react";
import { getReadme } from "../lib/api";

export default function EvidenceView() {
  const [id, setId] = useState("");
  const [sections, setSections] = useState<any[]>([]);

  async function load() {
    const data = await getReadme(id);
    setSections(data.sections || []);
  }

  return (
    <div className="card">
      <h2>Evidence Drilldown</h2>
      <div className="row">
        <input value={id} onChange={(e) => setId(e.target.value)} placeholder="analysis id" />
        <button onClick={load}>Load</button>
      </div>
      {sections.map((section, idx) => (
        <div className="card" key={idx}>
          <h3>{section.title}</h3>
          <p>{section.content}</p>
          <pre>{JSON.stringify(section.evidence_refs, null, 2)}</pre>
        </div>
      ))}
    </div>
  );
}
