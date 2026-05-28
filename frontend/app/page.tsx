import Link from "next/link";

export default function Home() {
  return (
    <div className="card">
      <div className="row">
        <Link href="/analyze">Analyze</Link>
        <Link href="/status">Run Status</Link>
        <Link href="/report">Report Explorer</Link>
        <Link href="/readme">README Export</Link>
        <Link href="/evidence">Evidence Drilldown</Link>
        <Link href="/share">Share Controls</Link>
      </div>
    </div>
  );
}
