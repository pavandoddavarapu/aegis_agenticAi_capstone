import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Aegis Clinical Intelligence — Patient Analysis Workspace",
  description: "AI-powered clinical decision support. Evidence-grounded patient analysis with human-in-the-loop governance.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={cn(inter.className, "min-h-screen bg-[#070b14] antialiased overflow-hidden")}>
        {children}
      </body>
    </html>
  );
}
