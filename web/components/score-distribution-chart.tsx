"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function ScoreDistributionChart({
  bins,
}: {
  bins: { pd: number; count: number }[];
}) {
  const data = bins.map((b) => ({
    bucket: `${Math.round(b.pd * 100)}%`,
    count: b.count,
  }));
  if (!data.length) {
    return <p className="text-sm text-slate-500">Distribution not available.</p>;
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: "#64748b" }} interval={3} />
          <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
          <Tooltip formatter={(v: number) => [v, "applicants"]} />
          <Bar dataKey="count" fill="#4f46e5" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
