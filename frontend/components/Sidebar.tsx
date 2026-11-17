"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity, BarChart3, Droplets, FileStack, FlaskConical, HeartPulse, History, LayoutDashboard, Menu, Upload, Waves, X,
} from "lucide-react";

const GROUPS = [
  {
    label: null,
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/upload", label: "Upload report", icon: Upload },
    ],
  },
  {
    label: "Analyses",
    items: [
      { href: "/ecg", label: "ECG", icon: Activity },
      { href: "/echo", label: "ECHO", icon: Waves },
      { href: "/blood", label: "Blood", icon: Droplets },
      { href: "/liver", label: "Liver", icon: FlaskConical },
      { href: "/lipid", label: "Lipid profile", icon: HeartPulse },
    ],
  },
  {
    label: "Records",
    items: [
      { href: "/summary", label: "Combined summary", icon: FileStack },
      { href: "/history", label: "Report history", icon: History },
      { href: "/models", label: "Model performance", icon: BarChart3 },
    ],
  },
];

/** Flat mark: the reference-range tick (a track, the normal band and a value tick) – the product's signature */
function Mark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden>
      <rect width="20" height="20" rx="5" fill="#0b2545" />
      <rect x="4" y="9" width="12" height="2" rx="1" fill="#ffffff" fillOpacity="0.35" />
      <rect x="7" y="9" width="6" height="2" fill="#ffffff" fillOpacity="0.8" />
      <rect x="11" y="5.5" width="1.5" height="9" rx="0.75" fill="#ffffff" />
    </svg>
  );
}

export default function Sidebar() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="fixed left-3 top-2 z-40 rounded-lg border border-slate-900/10 bg-white p-1.5 text-slate-700 md:hidden"
        onClick={() => setOpen(!open)} aria-label="Toggle navigation">
        {open ? <X size={16} strokeWidth={1.5} /> : <Menu size={16} strokeWidth={1.5} />}
      </button>
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-60 shrink-0 flex-col border-r border-slate-900/[0.08] bg-slate-100/60 backdrop-blur-0 transition-transform duration-200 ease-out md:static md:translate-x-0 ${open ? "translate-x-0 bg-slate-50" : "-translate-x-full"}`}>
        <div className="flex h-14 items-center gap-2 px-5">
          <Mark />
          <span className="text-[17px] font-medium tracking-[-0.01em] text-navy-900">MediScan AI</span>
        </div>
        <nav className="flex-1 px-3 pt-2" aria-label="Main">
          {GROUPS.map((g, gi) => (
            <div key={gi} className={gi ? "mt-6" : ""}>
              {g.label && <div className="mb-2 px-3 text-xs font-medium text-slate-500">{g.label}</div>}
              <div className="space-y-0.5">
                {g.items.map(({ href, label, icon: Icon }) => {
                  const active = href === "/" ? path === "/" : path.startsWith(href);
                  return (
                    <Link key={href} href={href} onClick={() => setOpen(false)}
                      className={`flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm transition-colors duration-150 ${active ? "bg-white font-medium text-navy-900 shadow-[0_1px_2px_rgba(15,23,42,0.06)] ring-1 ring-slate-900/[0.06]" : "text-slate-600 hover:bg-white/70 hover:text-slate-900"}`}>
                      <Icon size={16} strokeWidth={1.5} className={active ? "text-teal-700" : "text-slate-500"} />
                      {label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <p className="px-5 pb-5 text-xs leading-4 text-slate-500">
          Reports are read on your server with Tesseract OCR. Nothing is sent to an external AI service
        </p>
      </aside>
    </>
  );
}
