"use client";

import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell } from 'recharts';
import { Activity, TrendingUp, ShieldAlert, Crosshair } from "lucide-react";
import { format } from "date-fns";

export default function MetricsDashboard() {
  const [evalRuns, setEvalRuns] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchMetrics() {
      try {
        const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";
        
        const [runsRes, statsRes] = await Promise.all([
          fetch(`${gatewayUrl}/v1/metrics/eval-runs`),
          fetch(`${gatewayUrl}/v1/metrics/stats`)
        ]);

        if (runsRes.ok) {
          const runs = await runsRes.json();
          // Format data for charts
          const formattedRuns = runs.map((r: any) => ({
            ...r,
            displayTime: format(new Date(r.created_at), "HH:mm:ss"),
            f1_pct: Math.round(r.f1_score * 100),
            fp_pct: Math.round(r.fp_rate * 100),
            fn_pct: Math.round(r.fn_rate * 100),
          }));
          setEvalRuns(formattedRuns);
        }
        
        if (statsRes.ok) {
          setStats(await statsRes.json());
        }
      } catch (err) {
        console.error("Failed to fetch metrics", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchMetrics();
    // In a real app we might poll this every 30s
  }, []);

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-neutral-500 gap-4">
        <Activity className="animate-spin opacity-50" size={48} />
        <p className="font-medium tracking-wide">Loading metrics...</p>
      </div>
    );
  }

  const latestRun = evalRuns.length > 0 ? evalRuns[evalRuns.length - 1] : null;

  const pieData = stats ? [
    { name: 'Overridden', value: stats.total_overrides },
    { name: 'Maintained', value: stats.total_blocks - stats.total_overrides }
  ] : [];
  const pieColors = ['#b3771a', '#c0392f']; // edit (override), block

  return (
    <div className="h-full flex flex-col overflow-y-auto pb-10">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Metrics & Evals</h1>
          <p className="text-neutral-400">Live CI eval runs and production feedback loops</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6 mb-6">
        <div className="glass p-6 rounded-2xl flex flex-col gap-2">
          <div className="flex items-center gap-2 text-neutral-400 font-semibold uppercase tracking-wider text-xs">
            <Crosshair size={16} /> Latest F1 Score
          </div>
          <div className="text-4xl font-bold text-white">
            {latestRun ? `${latestRun.f1_pct}%` : "N/A"}
          </div>
          <p className="text-xs text-neutral-500">Based on {latestRun?.total_examples || 0} corpus examples</p>
        </div>

        <div className="glass p-6 rounded-2xl flex flex-col gap-2">
          <div className="flex items-center gap-2 text-neutral-400 font-semibold uppercase tracking-wider text-xs">
            <TrendingUp size={16} /> False Positive Rate
          </div>
          <div className="text-4xl font-bold text-allow">
            {latestRun ? `${latestRun.fp_pct}%` : "N/A"}
          </div>
          <p className="text-xs text-neutral-500">Target &lt; 5%</p>
        </div>

        <div className="glass p-6 rounded-2xl flex flex-col gap-2">
          <div className="flex items-center gap-2 text-neutral-400 font-semibold uppercase tracking-wider text-xs">
            <ShieldAlert size={16} /> Override Rate
          </div>
          <div className="text-4xl font-bold text-edit">
            {stats ? `${Math.round(stats.override_rate * 100)}%` : "N/A"}
          </div>
          <p className="text-xs text-neutral-500">{stats?.total_overrides || 0} manual overrides</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 h-96">
        {/* FP / FN Trend Line Chart */}
        <div className="glass p-6 rounded-2xl flex flex-col">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-400 mb-6">Eval Run Trend (FP/FN)</h2>
          <div className="flex-1 w-full h-full min-h-0">
            {evalRuns.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={evalRuns} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorFp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#c0392f" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#c0392f" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorFn" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#b3771a" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#b3771a" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                  <XAxis dataKey="displayTime" stroke="#666" tick={{fill: '#666', fontSize: 12}} />
                  <YAxis stroke="#666" tick={{fill: '#666', fontSize: 12}} />
                  <RechartsTooltip 
                    contentStyle={{ backgroundColor: '#171717', borderColor: '#333', borderRadius: '8px' }}
                    itemStyle={{ color: '#e5e5e5' }}
                  />
                  <Area type="monotone" dataKey="fp_pct" name="False Positives %" stroke="#c0392f" fillOpacity={1} fill="url(#colorFp)" />
                  <Area type="monotone" dataKey="fn_pct" name="False Negatives %" stroke="#b3771a" fillOpacity={1} fill="url(#colorFn)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-neutral-600 text-sm">No eval runs recorded yet.</div>
            )}
          </div>
        </div>

        {/* Override Rate Pie Chart */}
        <div className="glass p-6 rounded-2xl flex flex-col">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-400 mb-6">Production Blocks vs Overrides</h2>
          <div className="flex-1 w-full h-full min-h-0 flex items-center justify-center">
            {stats && stats.total_blocks > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip 
                    contentStyle={{ backgroundColor: '#171717', borderColor: '#333', borderRadius: '8px' }}
                    itemStyle={{ color: '#e5e5e5' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-neutral-600 text-sm flex flex-col items-center gap-2">
                <ShieldAlert size={24} className="opacity-50" />
                No block interactions recorded yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
