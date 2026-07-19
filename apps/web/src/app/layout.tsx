import "@fontsource-variable/dm-sans";
import "./globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "B2 Speaking Practice — Academia",
  description: "Simulador interno para practicar Cambridge B2 First Speaking.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
