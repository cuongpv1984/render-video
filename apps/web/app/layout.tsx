import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {title: "Frame Studio · AI Animation", description: "Studio sản xuất hoạt hình với ngân sách rõ ràng và Balanced Mode."};
export default function Layout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="vi"><body>{children}</body></html>;
}
