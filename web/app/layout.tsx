import type { Metadata } from "next";
import { Bricolage_Grotesque, Public_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";

/* Three faces, three jobs -- a stricter split than most systems.
   Display carries the personality, body carries the sentences and has none of
   its own, mono marks anything machine-shaped. Weights are loaded narrowly on
   purpose: don't request what you won't use. */
const bricolage = Bricolage_Grotesque({
  variable: "--font-bricolage",
  weight: ["600", "800"],
  display: "swap",
  subsets: ["latin"],
});

const publicSans = Public_Sans({
  variable: "--font-public-sans",
  weight: ["400", "500", "600"],
  display: "swap",
  subsets: ["latin"],
});

const jetbrains = JetBrains_Mono({
  variable: "--font-jetbrains",
  weight: ["400", "500"],
  display: "swap",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Kestrel",
  description:
    "DataHub's Metadata Tests check one entity at a time. Kestrel checks conditions across the lineage graph — and writes the findings back into the catalog.",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${bricolage.variable} ${publicSans.variable} ${jetbrains.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
