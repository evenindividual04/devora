"use client";

import { useState } from "react";
import { createShare, revokeShare } from "../lib/api";

export default function ShareControls() {
  const [analysisId, setAnalysisId] = useState("");
  const [ttl, setTtl] = useState(1440);
  const [share, setShare] = useState<any>(null);

  async function create() {
    setShare(await createShare(analysisId, ttl));
  }

  async function revoke() {
    if (!share?.token) return;
    await revokeShare(share.token);
    setShare({ ...share, revoked: true });
  }

  return (
    <div className="card">
      <h2>Share Controls</h2>
      <div className="row">
        <input value={analysisId} onChange={(e) => setAnalysisId(e.target.value)} placeholder="analysis id" />
        <input type="number" value={ttl} onChange={(e) => setTtl(Number(e.target.value))} />
        <button onClick={create}>Create share link</button>
      </div>
      <pre>{JSON.stringify(share, null, 2)}</pre>
      <div className="row"><button onClick={revoke}>Revoke share</button></div>
    </div>
  );
}
