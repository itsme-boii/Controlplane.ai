"use client";

import { useEffect, useState, useRef } from "react";
import { format } from "date-fns";
import { ShieldCheck, ShieldAlert, AlertTriangle, XCircle, Search, Activity } from "lucide-react";
import Link from "next/link";

type AuditRecord = {
  request_id: string;
  created_at: string;
  decision: string;
  usecase_id: string;
};

export default function LiveFeed() {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    // Use a hardcoded gateway URL for development prototype
    const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
    const eventSource = new EventSource(`${gatewayUrl}/v1/audit/stream`);

    eventSource.onopen = () => setIsConnected(true);
    
    eventSource.onmessage = (event) => {
      try {
        const record: AuditRecord = JSON.parse(event.data);
        setRecords((prev) => [record, ...prev].slice(0, 100)); // Keep last 100
      } catch (err) {
        console.error("Failed to parse SSE", err);
      }
    };

    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();
      // Basic reconnect logic could go here
    };

    return () => {
      eventSource.close();
    };
  }, []);

  const getTierConfig = (tier: string) => {
    switch (tier) {
      case "allow":
        return { icon: <ShieldCheck size={14} />, badgeClass: "badge-allow" };
      case "edit":
        return { icon: <AlertTriangle size={14} />, badgeClass: "badge-edit" };
      case "review":
        return { icon: <ShieldAlert size={14} />, badgeClass: "badge-review" };
      case "block":
        return { icon: <XCircle size={14} />, badgeClass: "badge-block" };
      default:
        return { icon: <Search size={14} />, badgeClass: "bg-neutral-800 text-neutral-300" };
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Live Feed</h1>
          <p className="text-neutral-400">Real-time gateway interactions</p>
        </div>
        <div className="flex items-center gap-3 glass px-4 py-2 rounded-full">
          <div className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-allow animate-pulse shadow-[0_0_8px_#2f8f5b]" : "bg-block"}`}></div>
          <span className="text-sm font-semibold text-neutral-300 uppercase tracking-wider">{isConnected ? "Connected" : "Disconnected"}</span>
        </div>
      </div>

      <div className="glass flex-1 rounded-2xl overflow-hidden flex flex-col">
        <div className="grid grid-cols-12 gap-4 p-4 border-b border-neutral-800/50 bg-neutral-900/30 text-xs font-semibold uppercase tracking-wider text-neutral-500">
          <div className="col-span-2">Time</div>
          <div className="col-span-5">Request ID</div>
          <div className="col-span-3">Usecase</div>
          <div className="col-span-2 text-right">Decision</div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {records.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-4">
              <Activity className="animate-pulse opacity-50" size={48} />
              <p className="font-medium tracking-wide">Waiting for gateway traffic...</p>
            </div>
          ) : (
            records.map((r, i) => {
              const { icon, badgeClass } = getTierConfig(r.decision);
              return (
                <Link key={`${r.request_id}-${i}`} href={`/queue/${r.request_id}`} className="grid grid-cols-12 gap-4 p-3 rounded-xl hover:bg-neutral-800/60 transition-colors items-center text-sm group cursor-pointer block border border-transparent hover:border-neutral-700/50">
                  <div className="col-span-2 text-neutral-400 font-mono text-xs group-hover:text-neutral-300 transition-colors">
                    {format(new Date(r.created_at), "HH:mm:ss.SSS")}
                  </div>
                  <div className="col-span-5 font-mono text-xs text-neutral-300 truncate group-hover:text-white transition-colors">
                    {r.request_id}
                  </div>
                  <div className="col-span-3 text-neutral-300 font-medium group-hover:text-white transition-colors">
                    {r.usecase_id}
                  </div>
                  <div className="col-span-2 flex justify-end">
                    <span className={`badge flex items-center gap-1.5 ${badgeClass}`}>
                      {icon}
                      {r.decision}
                    </span>
                  </div>
                </Link>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
