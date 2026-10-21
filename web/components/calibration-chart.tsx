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
  variant = "light",
}: {
  curve: { mean_predicted: number | null; observed_rate: number | null; count: number }[];
  variant?: "light" | "dark";
}) {
  const dark = variant === "dark";
  const axis = dark ? "#A8977C" : "#857560";
  const grid = dark ? "#362F25" : "#E2D6C0";
  const line = dark ? "#D8A65A" : "#A64420";
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
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis
            dataKey="predicted"
            unit="%"
            tick={{ fontSize: 11, fill: axis }}
            label={{ value: "Predicted risk (%)", position: "insideBottom", offset: -4, fontSize: 11, fill: axis }}
          />
          <YAxis
            unit="%"
            tick={{ fontSize: 11, fill: axis }}
            label={{ value: "Observed default rate (%)", angle: -90, position: "insideLeft", fontSize: 11, fill: axis }}
          />
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
            formatter={(value: number) => [`${value}%`, ""]}
            labelFormatter={(l) => `Predicted ${l}%`}
          />
          <ReferenceLine
            segment={[
              { x: 0, y: 0 },
              { x: 100, y: 100 },
            ]}
            stroke={dark ? "#5A4E3D" : "#CBBBA0"}
            strokeDasharray="4 4"
          />
          <Line
            type="monotone"
            dataKey="observed"
            stroke={line}
            strokeWidth={1.75}
            dot={{ r: 3, strokeWidth: 1 }}
            name="Observed"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
