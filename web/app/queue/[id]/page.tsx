"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Activity, ArrowLeft, Check, X, Edit3, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function DetailView({ params }: { params: { id: string } }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const router = useRouter();

  useEffect(() => {
    async function fetchRecord() {
      try {
        const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
        const res = await fetch(`${gatewayUrl}/v1/audit/records/${params.id}`);
        if (res.ok) {
          const json = await res.json();
          setData(json);
        }
      } catch (err) {
        console.error("Failed to fetch detail", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchRecord();
  }, [params.id]);

  const handleReview = async (action: string) => {
    setIsSubmitting(true);
    try {
      const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
      const res = await fetch(`${gatewayUrl}/v1/audit/records/${params.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reviewer_id: "human-reviewer-1" })
      });
      if (res.ok) {
        router.push("/queue");
      }
    } catch (err) {
      console.error("Failed to submit review", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-4">
        <Activity className="animate-spin opacity-50" size={48} />
        <p className="font-medium tracking-wide">Loading evidence...</p>
      </div>
    );
  }

  if (!data || !data.record) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-4">
        <ShieldAlert className="opacity-20" size={64} />
        <p className="font-medium tracking-wide text-xl">Record not found</p>
        <Link href="/queue" className="text-review hover:underline mt-4">Return to Queue</Link>
      </div>
    );
  }

  const { record, reviews } = data;

  return (
    <div className="h-full flex flex-col overflow-y-auto pb-10">
      <div className="flex items-center gap-4 mb-8">
        <Link href="/queue" className="p-2 glass rounded-full text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors">
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white mb-1 flex items-center gap-3">
            Interaction Detail
            <span className={`badge ${record.decision === "review" ? "badge-review" : record.decision === "allow" ? "badge-allow" : "badge-block"}`}>
              {record.decision}
            </span>
          </h1>
          <p className="text-neutral-500 font-mono text-sm">{record.request_id}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-6">
          <div className="glass p-6 rounded-2xl">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-500 mb-4">Prompt</h2>
            <div className="bg-neutral-950 p-4 rounded-xl font-mono text-sm text-neutral-300 border border-neutral-800/50">
              {record.request_body?.messages?.[record.request_body.messages.length - 1]?.content || JSON.stringify(record.request_body)}
            </div>
          </div>
          
          <div className="glass p-6 rounded-2xl">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-500 mb-4">Upstream Response</h2>
            <div className="bg-neutral-950 p-4 rounded-xl font-mono text-sm text-neutral-300 border border-neutral-800/50 whitespace-pre-wrap">
              {record.response_body?.choices?.[0]?.message?.content || JSON.stringify(record.response_body)}
            </div>
          </div>
          
          <div className="glass p-6 rounded-2xl">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-500 mb-4">Detector Evidence</h2>
            <div className="space-y-3">
              {record.detector_results?.map((det: any, i: number) => (
                <div key={i} className="bg-neutral-950/50 p-4 rounded-xl border border-neutral-800/50 flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-neutral-200 capitalize">{det.detector}</h3>
                    {det.rationale && <p className="text-sm text-neutral-400 mt-1">{det.rationale}</p>}
                    {det.spans && det.spans.length > 0 && (
                      <div className="mt-2 text-xs font-mono text-neutral-500">
                        {det.spans.map((s: any, j: number) => (
                          <div key={j}>Span: {s.label ?? "match"} &quot;{s.text}&quot;</div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-neutral-300">Confidence: {det.confidence.toFixed(2)}</div>
                    <div className="text-xs text-neutral-500 mt-1">
                      {typeof det.latency_ms === "number" ? `${det.latency_ms.toFixed(1)}ms` : "—"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="col-span-1 space-y-6">
          <div className="glass p-6 rounded-2xl">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-500 mb-4">Metadata</h2>
            <dl className="space-y-4 text-sm">
              <div>
                <dt className="text-neutral-500">Created At</dt>
                <dd className="text-neutral-200 font-medium">{format(new Date(record.created_at), "PP pp")}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">Usecase</dt>
                <dd className="text-neutral-200 font-medium">{record.usecase_id}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">Jurisdiction</dt>
                <dd className="text-neutral-200 font-medium">{record.jurisdiction}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">Latency</dt>
                <dd className="text-neutral-200 font-medium">{record.gateway_latency_ms?.toFixed(1)}ms (Gateway)</dd>
              </div>
            </dl>
          </div>

          <div className="glass p-6 rounded-2xl bg-review/5 border-review/20 shadow-[0_0_30px_rgba(58,110,168,0.1)]">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-review mb-4">Reviewer Actions</h2>
            
            {reviews.length > 0 ? (
              <div className="mb-6 space-y-3">
                {reviews.map((r: any, i: number) => (
                  <div key={i} className="bg-neutral-950 p-3 rounded-xl border border-neutral-800 text-sm">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-neutral-200 capitalize">{r.action}</span>
                      <span className="text-xs text-neutral-500">{format(new Date(r.created_at), "MMM d, HH:mm")}</span>
                    </div>
                    <div className="text-neutral-400 text-xs">by {r.reviewer_id}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-neutral-500 mb-6 italic">No review actions yet.</p>
            )}

            <div className="flex flex-col gap-3">
              <button 
                onClick={() => handleReview("approve")}
                disabled={isSubmitting}
                className="w-full flex items-center justify-center gap-2 bg-allow/20 hover:bg-allow/30 text-allow font-semibold py-2.5 rounded-xl border border-allow/30 transition-colors disabled:opacity-50"
              >
                <ShieldCheck size={18} />
                Override to Allow
              </button>
              <button 
                onClick={() => handleReview("reject")}
                disabled={isSubmitting}
                className="w-full flex items-center justify-center gap-2 bg-block/20 hover:bg-block/30 text-block font-semibold py-2.5 rounded-xl border border-block/30 transition-colors disabled:opacity-50"
              >
                <X size={18} />
                Keep Blocked
              </button>
              <button 
                onClick={() => handleReview("edit")}
                disabled={isSubmitting}
                className="w-full flex items-center justify-center gap-2 bg-edit/20 hover:bg-edit/30 text-edit font-semibold py-2.5 rounded-xl border border-edit/30 transition-colors disabled:opacity-50"
              >
                <Edit3 size={18} />
                Edit & Approve
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
