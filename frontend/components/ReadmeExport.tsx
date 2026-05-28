"use client";

import { useState } from "react";
import { getReadme } from "../lib/api";

export default function ReadmeExport() {
  const [id, setId] = useState("");
  const [md, setMd] = useState("");

  async function load() {
    const data = await getReadme(id);
    setMd(data.markdown || "");
  }

  function download() {
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "README.generated.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="card">
      <h2>README Export</h2>
      <div className="row">
        <input value={id} onChange={(e) => setId(e.target.value)} placeholder="analysis id" />
        <button onClick={load}>Load</button>
        <button onClick={download}>Download</button>
      </div>
      <textarea value={md} onChange={(e) => setMd(e.target.value)} rows={18} style={{ width: "100%" }} />
    </div>
  );
}
