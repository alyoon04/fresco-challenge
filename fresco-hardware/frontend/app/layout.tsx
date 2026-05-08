/**
 * Root layout for the Fresco Hardware Sets UI.
 *
 * Three-pane interface:
 *   Left:   PDF viewer (react-pdf) with bbox overlays
 *   Center: Extracted hardware sets list
 *   Right:  Set detail / edit panel for feedback corrections
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Fresco — Hardware Sets Extractor",
  description: "Extract and review hardware sets from Division 08 specbooks",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
