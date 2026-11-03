import type { Metadata } from "next";

import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Customer Portal · Select Exterminating",
  description: "Select Exterminating customer portal",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-background text-sm text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
