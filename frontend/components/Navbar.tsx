"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getAccessToken, clearTokens } from "../lib/auth";

export default function Navbar() {
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(!!getAccessToken());
    const handler = () => setAuthed(!!getAccessToken());
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, []);

  return (
    <div className="card">
      <div className="row">
        <Link href="/analyze" style={{ fontWeight: 600 }}>Devora</Link>
        <Link href="/analyze">Analyze</Link>
        {authed && <Link href="/share">Shares</Link>}
        {authed ? (
          <button onClick={() => { clearTokens(); setAuthed(false); }}>Log out</button>
        ) : (
          <Link href="/analyze">Log in</Link>
        )}
      </div>
    </div>
  );
}
