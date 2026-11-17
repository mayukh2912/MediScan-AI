import type { Metadata } from "next";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "MediScan AI – Medical Report Intelligence",
  description: "Transform Medical Reports Into Understandable Health Insights. Educational research prototype.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="border-b border-slate-900/[0.08] bg-white px-6 py-2 pl-16 text-xs leading-4 text-slate-600 md:pl-8" role="note">
              <span className="font-medium text-slate-900">Educational research prototype.</span> Not a medical device and not clinically validated. Results
              are not a diagnosis; a qualified healthcare professional must interpret them.
            </div>
            <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-8 md:px-8">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
