import "./globals.css";
import type { ReactNode } from "react";
import Navbar from "../components/Navbar";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="container">
          <h1>Devora GitHub Profile Analyzer</h1>
          <p>Private beta flow: login, analyze, inspect evidence, export, share.</p>
          <Navbar />
          {children}
        </div>
      </body>
    </html>
  );
}
