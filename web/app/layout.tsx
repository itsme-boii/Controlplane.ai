import type { Metadata } from "next";
import Link from "next/link";
import { Activity, ShieldAlert, FileText, Settings, LineChart } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "ControlPlane.ai — Review Console",
  description: "Governance control plane for enterprise AI interactions",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="flex h-screen bg-neutral-950 text-neutral-300 antialiased overflow-hidden selection:bg-review/30">
        
        {/* Sidebar */}
        <aside className="w-64 flex-shrink-0 glass flex flex-col justify-between border-r border-neutral-800 z-10 relative">
          <div className="absolute inset-0 bg-gradient-to-b from-review/5 to-transparent pointer-events-none"></div>
          <div className="p-6 relative z-10">
            <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-review to-edit flex items-center justify-center shadow-[0_0_20px_rgba(58,110,168,0.3)]">
                <ShieldAlert size={20} className="text-white drop-shadow-sm" />
              </div>
              ControlPlane
            </h1>
            
            <nav className="mt-12 flex flex-col gap-2">
              <NavItem href="/" icon={<Activity size={18} />} label="Live Feed" />
              <NavItem href="/queue" icon={<ShieldAlert size={18} />} label="Review Queue" />
              <NavItem href="/policies" icon={<FileText size={18} />} label="Policies" />
              <NavItem href="/metrics" icon={<LineChart size={18} />} label="Metrics" />
            </nav>
          </div>
          
          <div className="p-6 relative z-10">
            <div className="flex items-center gap-3 text-sm text-neutral-500 hover:text-neutral-300 transition-colors cursor-pointer px-4 py-3 rounded-xl hover:bg-neutral-800/50">
              <Settings size={16} />
              <span className="font-medium">Settings</span>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 relative overflow-y-auto bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-neutral-900 via-neutral-950 to-neutral-950">
          <div className="absolute inset-0 bg-gradient-to-br from-review/5 via-transparent to-block/5 pointer-events-none"></div>
          <div className="relative z-10 h-full p-8 max-w-7xl mx-auto">
            {children}
          </div>
        </main>
        
      </body>
    </html>
  );
}

function NavItem({ href, icon, label }: { href: string; icon: React.ReactNode; label: string }) {
  return (
    <Link 
      href={href} 
      className="flex items-center gap-3 px-4 py-3 rounded-xl text-neutral-400 hover:text-white hover:bg-neutral-800/50 transition-all group border border-transparent hover:border-neutral-700/50"
    >
      <span className="group-hover:text-review transition-colors drop-shadow-[0_0_8px_rgba(58,110,168,0.5)]">{icon}</span>
      <span className="font-medium text-sm tracking-wide">{label}</span>
    </Link>
  );
}
