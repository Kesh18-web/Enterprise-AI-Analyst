import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

export const metadata: Metadata = {
  title: "Enterprise AI Analyst | Multi-Agent Runtime Command Center",
  description:
    "Flagship Enterprise AI Analyst platform built with LangGraph, Qdrant Hybrid RRF, Cross-Encoder Reranker, and Firebase Firestore.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <body className="min-h-screen bg-[#090d16] text-slate-100 font-sans antialiased selection:bg-indigo-500 selection:text-white">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
