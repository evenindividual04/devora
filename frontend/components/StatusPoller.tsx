"use client";

import { useEffect, useState } from "react";
import { getStatus } from "../lib/api";

export default function StatusPoller() {
  const [id, setId] = useState("");
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("analysis_id") : null;
    if (saved) setId(saved);
  }, []);

  useEffect(() => {
    if (!id) return;
    let active = true;
    let timeout = 400;
    async function tick() {
      if (!active) return;
      try {
        const data = await getStatus(id);
        setStatus(data.status);
        if (data.status === "completed" || data.status === "failed_permanent") return;
      } catch {
        setStatus("error");
      }
      timeout = Math.min(timeout * 1.4, 2500);
      setTimeout(tick, timeout);
    }
    tick();
    return () => {
      active = false;
    };
  }, [id]);

  return (
    <div className="card">
      <h2>Run Status</h2>
      <input value={id} onChange={(e) => setId(e.target.value)} placeholder="analysis id" />
      <p>Status: <strong>{status}</strong></p>
    </div>
  );
}
