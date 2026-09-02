"use client";

import { useEffect, useState } from "react";
import { Activity, Save, FileText, AlertTriangle } from "lucide-react";

export default function Policies() {
  const [policies, setPolicies] = useState<string[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{type: "success" | "error", text: string} | null>(null);

  useEffect(() => {
    async function fetchPolicies() {
      try {
        const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
        const res = await fetch(`${gatewayUrl}/v1/policies`);
        if (res.ok) {
          const data = await res.json();
          setPolicies(data.policies);
          if (data.policies.length > 0) {
            selectPolicy(data.policies[0]);
          }
        }
      } catch (err) {
        console.error("Failed to fetch policies", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchPolicies();
  }, []);

  const selectPolicy = async (path: string) => {
    setSelectedPolicy(path);
    setMessage(null);
    try {
      const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
      const res = await fetch(`${gatewayUrl}/v1/policies/${path}`);
      if (res.ok) {
        const data = await res.json();
        setContent(data.content);
      }
    } catch (err) {
      console.error("Failed to fetch policy content", err);
    }
  };

  const savePolicy = async () => {
    if (!selectedPolicy) return;
    setSaving(true);
    setMessage(null);
    try {
      const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
      const res = await fetch(`${gatewayUrl}/v1/policies/${selectedPolicy}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content })
      });
      if (res.ok) {
        setMessage({ type: "success", text: "Policy saved successfully" });
        setTimeout(() => setMessage(null), 3000);
      } else {
        setMessage({ type: "error", text: "Failed to save policy" });
      }
    } catch (err) {
      console.error("Failed to save policy", err);
      setMessage({ type: "error", text: "Network error saving policy" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Policies</h1>
          <p className="text-neutral-400">Manage YAML policy configurations</p>
        </div>
      </div>

      <div className="flex-1 flex gap-6 overflow-hidden pb-10">
        {/* Policy List */}
        <div className="w-1/4 glass rounded-2xl p-4 flex flex-col">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-500 mb-4 px-2">Files</h2>
          <div className="flex-1 overflow-y-auto space-y-1">
            {loading ? (
              <div className="flex justify-center p-8 text-neutral-500"><Activity className="animate-spin opacity-50" /></div>
            ) : policies.length === 0 ? (
              <p className="text-neutral-500 text-sm px-2">No policies found.</p>
            ) : (
              policies.map((p) => (
                <button
                  key={p}
                  onClick={() => selectPolicy(p)}
                  className={`w-full text-left px-4 py-3 rounded-xl flex items-center gap-3 transition-colors ${
                    selectedPolicy === p 
                      ? "bg-edit/20 text-edit border border-edit/30 font-medium" 
                      : "text-neutral-400 hover:text-white hover:bg-neutral-800/50 border border-transparent"
                  }`}
                >
                  <FileText size={16} />
                  <span className="truncate text-sm">{p}</span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Editor */}
        <div className="flex-1 glass rounded-2xl flex flex-col overflow-hidden relative">
          <div className="p-4 border-b border-neutral-800/50 flex justify-between items-center bg-neutral-900/30">
            <h2 className="font-mono text-sm text-neutral-300 font-medium flex items-center gap-2">
              {selectedPolicy || "Select a policy"}
            </h2>
            <button
              onClick={savePolicy}
              disabled={!selectedPolicy || saving}
              className="flex items-center gap-2 bg-edit/20 hover:bg-edit/30 text-edit px-4 py-2 rounded-lg font-semibold text-sm transition-colors border border-edit/30 disabled:opacity-50"
            >
              {saving ? <Activity size={16} className="animate-spin" /> : <Save size={16} />}
              Save Changes
            </button>
          </div>
          
          {message && (
            <div className={`absolute top-16 right-4 p-3 rounded-lg flex items-center gap-2 text-sm font-medium z-10 shadow-lg ${
              message.type === "success" ? "bg-allow text-white" : "bg-block text-white"
            }`}>
              {message.type === "error" && <AlertTriangle size={16} />}
              {message.text}
            </div>
          )}

          <div className="flex-1 bg-neutral-950 p-6 overflow-y-auto">
            {selectedPolicy ? (
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="w-full h-full min-h-[500px] bg-transparent text-neutral-300 font-mono text-sm focus:outline-none resize-none leading-relaxed"
                spellCheck={false}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-neutral-600">
                <p>Select a policy file from the sidebar to edit.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
