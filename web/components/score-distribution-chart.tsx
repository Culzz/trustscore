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
  variant = "light",
}: {
  bins: { pd: number; count: number }[];
  variant?: "light" | "dark";
}) {
  const dark = variant === "dark";
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
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={dark ? "#362F25" : "#E2D6C0"}
            vertical={false}
          />
          <XAxis
            dataKey="bucket"
            tick={{ fontSize: 10, fill: dark ? "#A8977C" : "#857560" }}
            interval={3}
          />
          <YAxis tick={{ fontSize: 11, fill: dark ? "#A8977C" : "#857560" }} />
          <Tooltip
            contentStyle={
              dark
                ? {
                    background: "#15110C",
                    border: "1px solid #362F25",
                    borderRadius: 3,
                    fontSize: 11,
                    color: "#F0E8D8",
                  }
                : {
                    background: "#FCFAF3",
                    border: "1px solid #E2D6C0",
                    borderRadius: 3,
                    fontSize: 11,
                    color: "#241F18",
                  }
            }
            formatter={(v: number) => [v, "applicants"]}
          />
          <Bar
            dataKey="count"
            fill={dark ? "#CD9837" : "#A64420"}
            radius={[1, 1, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
