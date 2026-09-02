"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";
import { ShieldAlert, Activity } from "lucide-react";
import Link from "next/link";

type AuditRecord = {
  id: number;
  request_id: string;
  created_at: string;
  decision: string;
  usecase_id: string;
};

export default function ReviewQueue() {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchQueue() {
      try {
        const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
        // Fetch items held for review
        const res = await fetch(`${gatewayUrl}/v1/audit/records?tier=review`);
        if (res.ok) {
          const data = await res.json();
          setRecords(data);
        }
      } catch (err) {
        console.error("Failed to fetch queue", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchQueue();
  }, []);

  return (
    <div className="h-full flex flex-col">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Review Queue</h1>
          <p className="text-neutral-400">Interactions flagged for human review</p>
        </div>
        <div className="flex items-center gap-2 glass px-4 py-2 rounded-full">
          <span className="text-sm font-semibold text-review uppercase tracking-wider">{records.length} items pending</span>
        </div>
      </div>

      <div className="glass flex-1 rounded-2xl overflow-hidden flex flex-col">
        <div className="grid grid-cols-12 gap-4 p-4 border-b border-neutral-800/50 bg-neutral-900/30 text-xs font-semibold uppercase tracking-wider text-neutral-500">
          <div className="col-span-3">Time</div>
          <div className="col-span-6">Request ID</div>
          <div className="col-span-3">Usecase</div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loading ? (
             <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-4">
               <Activity className="animate-spin opacity-50" size={48} />
               <p className="font-medium tracking-wide">Loading queue...</p>
             </div>
          ) : records.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-4">
              <ShieldAlert className="opacity-20" size={64} />
              <p className="font-medium tracking-wide">No items currently require review.</p>
            </div>
          ) : (
            records.map((r) => (
              <Link key={r.request_id} href={`/queue/${r.request_id}`} className="grid grid-cols-12 gap-4 p-4 rounded-xl hover:bg-neutral-800/60 transition-colors items-center text-sm group cursor-pointer block border border-transparent hover:border-neutral-700/50">
                <div className="col-span-3 text-neutral-400 font-mono text-xs group-hover:text-neutral-300 transition-colors">
                  {format(new Date(r.created_at), "yyyy-MM-dd HH:mm:ss")}
                </div>
                <div className="col-span-6 font-mono text-xs text-neutral-300 truncate group-hover:text-white transition-colors">
                  {r.request_id}
                </div>
                <div className="col-span-3 text-neutral-300 font-medium group-hover:text-white transition-colors flex items-center justify-between">
                  {r.usecase_id}
                  <span className="text-review group-hover:translate-x-1 transition-transform">→</span>
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
