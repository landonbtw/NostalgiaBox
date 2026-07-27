import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WonderBox",
  description: "The brain behind the WonderBox kids' question device.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
