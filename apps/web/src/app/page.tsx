import { SpeakingAcademyApp } from "@/features/practice/SpeakingAcademyApp";

// The CSP nonce is generated per request in proxy.ts. Keeping this route
// dynamic lets Next.js attach that nonce to its bootstrap and hydration
// scripts instead of reusing a nonce-less prerendered document.
export const dynamic = "force-dynamic";

export default function Home() {
  return <SpeakingAcademyApp />;
}
