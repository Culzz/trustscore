"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function CalibrationChart({
  curve,
}: {
  curve: { mean_predicted: number | null; observed_rate: number | null; count: number }[];
}) {
  const data = curve
    .filter((b) => b.mean_predicted !== null && b.observed_rate !== null)
    .map((b) => ({
      predicted: Number((b.mean_predicted! * 100).toFixed(1)),
      observed: Number((b.observed_rate! * 100).toFixed(1)),
      count: b.count,
    }));

  if (!data.length) {
    return <p className="text-sm text-slate-500">Calibration curve not available.</p>;
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="predicted"
            unit="%"
            tick={{ fontSize: 11, fill: "#64748b" }}
            label={{ value: "Predicted risk (%)", position: "insideBottom", offset: -4, fontSize: 11, fill: "#64748b" }}
          />
          <YAxis
            unit="%"
            tick={{ fontSize: 11, fill: "#64748b" }}
            label={{ value: "Observed default rate (%)", angle: -90, position: "insideLeft", fontSize: 11, fill: "#64748b" }}
          />
          <Tooltip
            formatter={(value: number) => [`${value}%`, ""]}
            labelFormatter={(l) => `Predicted ${l}%`}
          />
          <ReferenceLine
            segment={[
              { x: 0, y: 0 },
              { x: 100, y: 100 },
            ]}
            stroke="#94a3b8"
            strokeDasharray="4 4"
          />
          <Line
            type="monotone"
            dataKey="observed"
            stroke="#4f46e5"
            strokeWidth={2}
            dot={{ r: 3 }}
            name="Observed"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
