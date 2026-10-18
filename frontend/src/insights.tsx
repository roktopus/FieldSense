import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Legend,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import { MapReady, OSM_TILES, wellMarker } from "./OsmMap";

type Row = Record<string, unknown>;

type Donut = { type: "donut"; title: string; data: { name: string; value: number }[] };
type Bars = { type: "bar"; title: string; data: { name: string; value: number }[] };
type Hist = { type: "histogram"; title: string; data: { name: string; value: number }[] };
type Box = { type: "box"; title: string; label: string; values: number[] };
type Trend = { type: "area"; title: string; data: Record<string, string | number>[]; keys: string[] };
type Gantt = { type: "gantt"; title: string; rows: { name: string; start: number; end: number }[] };
type ScatterSpec = {
  type: "scatter";
  title: string;
  xLabel: string;
  yLabel: string;
  bubble: boolean;
  points: { x: number; y: number; z: number; name: string }[];
};
type Heat = { type: "heatmap"; title: string; xs: string[]; ys: string[]; cells: number[][] };
type Tree = { type: "treemap"; title: string; data: { name: string; size: number }[] };
type Bullet = { type: "bullet"; title: string; label: string; value: number; target: number };
type Flow = { type: "sankey"; title: string; links: { source: string; target: string; value: number }[] };
type Net = { type: "network"; title: string; links: { source: string; target: string; value: number }[] };
type Words = { type: "words"; title: string; words: { text: string; count: number }[] };
type MapSpec = { type: "map"; title: string; pins: { name: string; lat: number; lon: number }[] };
type Chart = Donut | Bars | Hist | Box | Trend | Gantt | ScatterSpec | Heat | Tree | Bullet | Flow | Net | Words | MapSpec;
type Kpi = { label: string; value: string };

const STATUS_COLOR: Record<string, string> = {
  met: "#3dd68c",
  yes: "#3dd68c",
  producing: "#3dd68c",
  compliant: "#3dd68c",
  missed: "#ff6b81",
  no: "#ff6b81",
  not_producing: "#ff6b81",
  "not producing": "#ff6b81",
};
const RAMP = ["#f4f4f4", "#b0b0b0", "#6e6e6e", "#3dd68c", "#ff6b81", "#e6c15a"];
const tip = { background: "#171717", border: "1px solid #2e2e2e", color: "#f5f5f5", fontSize: 12 };
const STOP = new Set(
  "the a an and or of to for in on at by with from as is are was were be this that it its we you they not no".split(" "),
);

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function has(rows: Row[], key: string): boolean {
  return rows.some((row) => row[key] != null && row[key] !== "");
}

function column(rows: Row[], names: string[]): string | null {
  return names.find((name) => has(rows, name)) ?? null;
}

function counts(rows: Row[], key: string): { name: string; value: number }[] {
  const map = new Map<string, number>();
  for (const row of rows) {
    const name = String(row[key] ?? "—");
    map.set(name, (map.get(name) || 0) + 1);
  }
  return [...map.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

function numbers(rows: Row[], key: string): number[] {
  return rows.map((row) => num(row[key])).filter((value): value is number => value != null);
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (!sorted.length) return 0;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function bins(values: number[]): { name: string; value: number }[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const count = 6;
  const span = max - min || 1;
  const width = span / count;
  const out = Array.from({ length: count }, (_, index) => ({
    name: `${trim(min + index * width)}–${trim(min + (index + 1) * width)}`,
    value: 0,
  }));
  for (const value of values) {
    const index = Math.min(count - 1, Math.floor((value - min) / width));
    out[index].value += 1;
  }
  return out;
}

function trim(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function stamp(value: unknown): number | null {
  if (value == null || value === "") return null;
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

const TITLES: Record<string, string> = {
  area_name: "Area",
  met: "Deadline",
  hours_to_response: "Hours to respond",
  wellhead_temp_c: "Wellhead",
  ambient_temp_c: "Ambient",
  downtime_days: "Downtime days",
  status_now: "Status now",
};

function label(key: string): string {
  if (TITLES[key]) return TITLES[key];
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function colorFor(name: string, index: number): string {
  return STATUS_COLOR[name.toLowerCase()] || RAMP[index % RAMP.length];
}

export function planInsights(rows: Row[]): { kpis: Kpi[]; charts: Chart[] } {
  if (!rows.length || typeof rows[0] !== "object") return { kpis: [], charts: [] };
  const charts: Chart[] = [];
  const lat = column(rows, ["lat", "latitude"]);
  const lon = column(rows, ["lon", "longitude"]);
  if (lat && lon) {
    charts.push({
      type: "map",
      title: "Where these records sit",
      pins: rows
        .map((row) => ({
          name: String(row.asset_id || row.area_name || "Well"),
          lat: Number(row[lat]),
          lon: Number(row[lon]),
        }))
        .filter((pin) => Number.isFinite(pin.lat) && Number.isFinite(pin.lon)),
    });
  }

  const startKey = column(rows, ["bypass_in", "start", "started_at", "start_at"]);
  const endKey = column(rows, ["bypass_out", "end", "ended_at", "end_at"]);
  if (startKey && endKey) {
    const intervals = rows
      .map((row) => ({
        name: String(row.asset_id || row.area_name || "Job"),
        start: stamp(row[startKey]),
        end: stamp(row[endKey]),
      }))
      .filter((row): row is { name: string; start: number; end: number } => row.start != null && row.end != null && row.end >= row.start)
      .slice(0, 18);
    if (intervals.length) charts.push({ type: "gantt", title: "Schedule", rows: intervals });
  }

  const timeKey = column(rows, ["inspected_at", "reported_at", "month", "date"]);
  const tempKeys = ["wellhead_temp_c", "ambient_temp_c"].filter((key) => has(rows, key));
  if (timeKey && tempKeys.length >= 1 && rows.length >= 3) {
    charts.push({
      type: "area",
      title: "Temperature over time",
      keys: tempKeys,
      data: rows.map((row) => {
        const point: Record<string, string | number> = { t: String(row[timeKey]).slice(0, 10) };
        for (const key of tempKeys) point[key] = num(row[key]) ?? 0;
        return point;
      }),
    });
  }

  const source = column(rows, ["source", "from"]);
  const target = column(rows, ["target", "to"]);
  const flowValue = column(rows, ["value", "volume_bbl", "count", "share_pct"]);
  if (source && target) {
    const links = new Map<string, number>();
    for (const row of rows) {
      const from = String(row[source]);
      const to = String(row[target]);
      const key = `${from}\u0000${to}`;
      links.set(key, (links.get(key) || 0) + (flowValue ? num(row[flowValue]) || 0 : 1));
    }
    const parsed = [...links.entries()].map(([key, value]) => {
      const [from, to] = key.split("\u0000");
      return { source: from, target: to, value };
    });
    if (flowValue) charts.push({ type: "sankey", title: "Flow", links: parsed });
    else charts.push({ type: "network", title: "Connections", links: parsed });
  }

  const statusKey = column(rows, ["met", "status", "status_now", "compliant", "approval", "response"]);
  const statusCounts = statusKey ? counts(rows, statusKey) : [];
  if (statusKey && statusCounts.length >= 2 && statusCounts.length <= 6) {
    charts.push({ type: "donut", title: label(statusKey), data: statusCounts });
  }

  const areaKey = column(rows, ["area_name", "well_type", "reason"]);
  if (areaKey && areaKey !== statusKey) {
    const ranked = counts(rows, areaKey).slice(0, 12);
    if (ranked.length >= 2) charts.push({ type: "bar", title: `Count by ${label(areaKey)}`, data: ranked });
    if (statusKey && statusCounts.length <= 6) {
      const xs = statusCounts.map((item) => item.name);
      const ys = ranked.map((item) => item.name);
      const cells = ys.map((area) =>
        xs.map((status) => rows.filter((row) => String(row[areaKey]) === area && String(row[statusKey]) === status).length),
      );
      charts.push({ type: "heatmap", title: `${label(areaKey)} × ${label(statusKey)}`, xs, ys, cells });
    }
  }

  const numericKey = column(rows, [
    "hours_to_response",
    "downtime_days",
    "delta_c",
    "mean_delta_c",
    "volume_bbl",
    "share_pct",
    "typical_extra_days",
  ]);
  const series = numericKey ? numbers(rows, numericKey) : [];
  if (numericKey && series.length >= 6 && new Set(series).size >= 4) {
    charts.push({ type: "histogram", title: label(numericKey), data: bins(series) });
    charts.push({ type: "box", title: "Spread", label: label(numericKey), values: series });
  }

  const numericCols = Object.keys(rows[0]).filter((key) => series.length && key !== numericKey && numbers(rows, key).length >= Math.min(6, rows.length));
  if (!charts.some((chart) => chart.type === "histogram") && numericCols.length >= 1 && numericKey) {
    const yKey = numericCols[0];
    const zKey = numericCols[1];
    charts.push({
      type: "scatter",
      title: `${label(numericKey)} vs ${label(yKey)}`,
      xLabel: label(numericKey),
      yLabel: label(yKey),
      bubble: Boolean(zKey),
      points: rows
        .map((row) => ({
          x: num(row[numericKey]),
          y: num(row[yKey]),
          z: zKey ? num(row[zKey]) || 8 : 8,
          name: String(row.asset_id || row.area_name || ""),
        }))
        .filter((point): point is { x: number; y: number; z: number; name: string } => point.x != null && point.y != null),
    });
  }

  if (areaKey && statusKey && !charts.some((chart) => chart.type === "treemap")) {
    const leaves = counts(rows, areaKey).slice(0, 10);
    if (leaves.length >= 3 && leaves.reduce((sum, item) => sum + item.value, 0) === rows.length) {
      charts.push({ type: "treemap", title: `Share by ${label(areaKey)}`, data: leaves.map((item) => ({ name: item.name, size: item.value })) });
    }
  }

  const deadline = column(rows, ["deadline_hours"]);
  if (statusKey === "met" && deadline && series.length) {
    const met = statusCounts.find((item) => item.name.toLowerCase() === "met")?.value || 0;
    charts.push({
      type: "bullet",
      title: "Against the deadline",
      label: "Met",
      value: Math.round((met / rows.length) * 100),
      target: 100,
    });
  }

  const textKey = column(rows, ["note_quote", "note", "text", "inspector_observation", "reason"]);
  if (textKey && charts.length < 3) {
    const freq = new Map<string, number>();
    for (const row of rows) {
      for (const word of String(row[textKey] || "").toLowerCase().match(/[a-z]{3,}/g) || []) {
        if (STOP.has(word)) continue;
        freq.set(word, (freq.get(word) || 0) + 1);
      }
    }
    const words = [...freq.entries()]
      .filter(([, count]) => count > 1)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 28)
      .map(([text, count]) => ({ text, count }));
    if (words.length >= 4) charts.push({ type: "words", title: "Language in the notes", words });
  }

  const kept = charts.slice(0, 4);
  const kpis: Kpi[] = [{ label: "Records", value: String(rows.length) }];
  if (statusCounts.length) {
    for (const item of statusCounts.slice(0, 3)) kpis.push({ label: item.name, value: String(item.value) });
  }
  if (series.length) kpis.push({ label: `Median ${label(numericKey || "value")}`, value: trim(median(series)) });
  return { kpis: kpis.slice(0, 4), charts: kept };
}

const axis = { fill: "#b0b0b0", fontSize: 11 };
const grid = "#2a2a2a";

export function InsightBoard({ rows, title }: { rows: Row[]; title?: string }) {
  const plan = useMemo(() => planInsights(rows), [rows]);
  if (!plan.charts.length && !plan.kpis.length) return null;
  return (
    <div className="space-y-3">
      {plan.kpis.length ? (
        <div className="grid grid-cols-2 overflow-hidden rounded-md border border-[var(--fs-border)] bg-paper sm:grid-cols-4">
          {plan.kpis.map((kpi) => (
            <div key={kpi.label} className="border-b border-r border-[var(--fs-border)] px-4 py-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-mute">{kpi.label}</div>
              <div className="mt-1 font-mono text-3xl font-medium tabular-nums tracking-tight text-ink">{kpi.value}</div>
            </div>
          ))}
        </div>
      ) : null}
      <div className="grid gap-3 lg:grid-cols-2">
        {plan.charts.map((chart, index) => (
          <article key={`${chart.type}-${index}`} className="rounded-lg border border-[var(--fs-border)] bg-paper p-3">
            <h3 className="mb-2 text-sm font-semibold text-ink">{chart.title}</h3>
            <ChartView chart={chart} />
          </article>
        ))}
      </div>
      <DetailTable title={title || "Records"} rows={rows} />
    </div>
  );
}

function ChartView({ chart }: { chart: Chart }) {
  if (chart.type === "donut") return <DonutChart data={chart.data} />;
  if (chart.type === "bar") return <RankChart data={chart.data} />;
  if (chart.type === "histogram") return <RankChart data={chart.data} vertical />;
  if (chart.type === "box") return <BoxPlot values={chart.values} label={chart.label} />;
  if (chart.type === "area") return <TrendChart data={chart.data} keys={chart.keys} />;
  if (chart.type === "gantt") return <GanttChart rows={chart.rows} />;
  if (chart.type === "scatter") return <ScatterPlot chart={chart} />;
  if (chart.type === "heatmap") return <HeatGrid chart={chart} />;
  if (chart.type === "treemap") return <TreeChart data={chart.data} />;
  if (chart.type === "bullet") return <BulletChart chart={chart} />;
  if (chart.type === "sankey" || chart.type === "network") return <FlowChart links={chart.links} weighted={chart.type === "sankey"} />;
  if (chart.type === "words") return <WordCloud words={chart.words} />;
  if (chart.type === "map") return <PinMap pins={chart.pins} />;
  return null;
}

function DonutChart({ data }: { data: { name: string; value: number }[] }) {
  return (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={74} paddingAngle={2} stroke="#171717">
            {data.map((item, index) => (
              <Cell key={item.name} fill={colorFor(item.name, index)} />
            ))}
          </Pie>
          <Tooltip contentStyle={tip} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function RankChart({ data, vertical = false }: { data: { name: string; value: number }[]; vertical?: boolean }) {
  return (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        {vertical ? (
          <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
            <CartesianGrid stroke={grid} vertical={false} />
            <XAxis dataKey="name" tick={axis} interval={0} angle={-18} textAnchor="end" height={48} />
            <YAxis tick={axis} allowDecimals={false} />
            <Tooltip contentStyle={tip} />
            <Bar dataKey="value" fill="#f2f2f2" radius={[3, 3, 0, 0]} />
          </BarChart>
        ) : (
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 12, top: 4, bottom: 4 }}>
            <CartesianGrid stroke={grid} horizontal={false} />
            <XAxis type="number" tick={axis} allowDecimals={false} />
            <YAxis type="category" dataKey="name" width={108} tick={axis} />
            <Tooltip contentStyle={tip} />
            <Bar dataKey="value" fill="#f2f2f2" radius={[0, 3, 3, 0]} barSize={16} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function TrendChart({ data, keys }: { data: Record<string, string | number>[]; keys: string[] }) {
  const strokes = ["#f2f2f2", "#0c6b45"];
  return (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid stroke={grid} />
          <XAxis dataKey="t" tick={axis} />
          <YAxis tick={axis} />
          <Tooltip contentStyle={tip} />
          {keys.map((key, index) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              name={label(key)}
              stroke={strokes[index % strokes.length]}
              fill={strokes[index % strokes.length]}
              fillOpacity={0.12}
              strokeWidth={2}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function ScatterPlot({ chart }: { chart: ScatterSpec }) {
  return (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid stroke={grid} />
          <XAxis dataKey="x" name={chart.xLabel} tick={axis} />
          <YAxis dataKey="y" name={chart.yLabel} tick={axis} />
          {chart.bubble ? <ZAxis dataKey="z" range={[40, 220]} /> : null}
          <Tooltip contentStyle={tip} cursor={{ strokeDasharray: "3 3" }} />
          <Scatter data={chart.points} fill="#f2f2f2" />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

function TreeChart({ data }: { data: { name: string; size: number }[] }) {
  return (
    <div className="h-52">
      <ResponsiveContainer width="100%" height="100%">
        <Treemap
          data={data}
          dataKey="size"
          nameKey="name"
          stroke="#171717"
          fill="#f2f2f2"
          content={<TreeCell />}
        />
      </ResponsiveContainer>
    </div>
  );
}

function TreeCell(props: { x?: number; y?: number; width?: number; height?: number; name?: string; index?: number }) {
  const { x = 0, y = 0, width = 0, height = 0, name, index = 0 } = props;
  if (width < 4 || height < 4) return null;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={RAMP[index % RAMP.length]} stroke="#171717" />
      {width > 48 && height > 18 ? (
        <text x={x + 6} y={y + 16} fill="#101010" fontSize={11}>
          {name}
        </text>
      ) : null}
    </g>
  );
}

function BoxPlot({ values, label: axisLabel }: { values: number[]; label: string }) {
  const sorted = [...values].sort((a, b) => a - b);
  const at = (p: number) => {
    const index = (sorted.length - 1) * p;
    const lo = Math.floor(index);
    const hi = Math.ceil(index);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (index - lo);
  };
  const stats = { min: sorted[0], q1: at(0.25), med: at(0.5), q3: at(0.75), max: sorted[sorted.length - 1] };
  const span = stats.max - stats.min || 1;
  const x = (value: number) => 16 + ((value - stats.min) / span) * 260;
  return (
    <svg viewBox="0 0 300 88" className="h-28 w-full" role="img" aria-label={axisLabel}>
      <line x1={x(stats.min)} x2={x(stats.max)} y1={40} y2={40} stroke="#f2f2f2" />
      <line x1={x(stats.min)} x2={x(stats.min)} y1={30} y2={50} stroke="#f2f2f2" />
      <line x1={x(stats.max)} x2={x(stats.max)} y1={30} y2={50} stroke="#f2f2f2" />
      <rect x={x(stats.q1)} y={24} width={Math.max(2, x(stats.q3) - x(stats.q1))} height={32} fill="#171717" stroke="#f2f2f2" />
      <line x1={x(stats.med)} x2={x(stats.med)} y1={24} y2={56} stroke="#0c6b45" strokeWidth={2} />
      <text x={16} y={78} fontSize={11} fill="#525252">
        {trim(stats.min)} to {trim(stats.max)} · median {trim(stats.med)}
      </text>
    </svg>
  );
}

function GanttChart({ rows }: { rows: { name: string; start: number; end: number }[] }) {
  const min = Math.min(...rows.map((row) => row.start));
  const max = Math.max(...rows.map((row) => row.end));
  const span = max - min || 1;
  const height = 28 + rows.length * 22;
  return (
    <svg viewBox={`0 0 320 ${height}`} className="w-full" style={{ height }}>
      {rows.map((row, index) => {
        const y = 16 + index * 22;
        const x = 88 + ((row.start - min) / span) * 220;
        const width = Math.max(3, ((row.end - row.start) / span) * 220);
        return (
          <g key={`${row.name}-${index}`}>
            <text x={0} y={y + 4} fontSize={11} fill="#f2f2f2">
              {row.name.slice(0, 12)}
            </text>
            <rect x={x} y={y - 8} width={width} height={12} rx={2} fill="#f2f2f2" />
          </g>
        );
      })}
    </svg>
  );
}

function HeatGrid({ chart }: { chart: Heat }) {
  const max = Math.max(...chart.cells.flat(), 1);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="text-mute">
            <th className="p-1 text-left font-medium" />
            {chart.xs.map((item) => (
              <th key={item} className="p-1 font-medium">
                {item}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {chart.ys.map((rowName, rowIndex) => (
            <tr key={rowName}>
              <td className="p-1 font-medium text-ink">{rowName}</td>
              {chart.cells[rowIndex].map((value, colIndex) => {
                const alpha = value === 0 ? 0.04 : 0.15 + (value / max) * 0.85;
                return (
                  <td
                    key={chart.xs[colIndex]}
                    className="p-1 text-center tabular-nums"
                    style={{ background: `rgba(255,255,255,${alpha})`, color: alpha > 0.55 ? "#101010" : "#f2f2f2" }}
                  >
                    {value}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BulletChart({ chart }: { chart: Bullet }) {
  const width = Math.max(0, Math.min(100, chart.value));
  return (
    <div>
      <div className="mb-2 text-xs text-mute">
        {chart.label} {chart.value}% · target {chart.target}%
      </div>
      <div className="relative h-7 overflow-hidden rounded bg-[#f4f4f4]">
        <div className="absolute inset-y-0 left-0 w-[70%] bg-[#e7e7e7]" />
        <div className="absolute inset-y-0 left-[70%] w-[20%] bg-[#d4d4d4]" />
        <div className="absolute inset-y-1 left-1 rounded-sm bg-[#f2f2f2]" style={{ width: `calc(${width}% - 8px)` }} />
        <div className="absolute inset-y-0 w-0.5 bg-[#0c6b45]" style={{ left: `${chart.target}%` }} />
      </div>
    </div>
  );
}

function FlowChart({ links, weighted }: { links: { source: string; target: string; value: number }[]; weighted: boolean }) {
  const sources = [...new Set(links.map((link) => link.source))].slice(0, 8);
  const targets = [...new Set(links.map((link) => link.target))].slice(0, 8);
  const yOf = (list: string[], name: string) => 18 + list.indexOf(name) * 28;
  const max = Math.max(...links.map((link) => link.value), 1);
  const height = Math.max(sources.length, targets.length) * 28 + 16;
  return (
    <svg viewBox={`0 0 320 ${height}`} className="w-full" style={{ height }}>
      {links.slice(0, 16).map((link, index) => {
        const y1 = yOf(sources, link.source);
        const y2 = yOf(targets, link.target);
        if (y1 < 18 || y2 < 18) return null;
        const width = weighted ? 1 + (link.value / max) * 8 : 1.5;
        return (
          <path
            key={index}
            d={`M90 ${y1} C150 ${y1}, 170 ${y2}, 230 ${y2}`}
            stroke="#f2f2f2"
            strokeOpacity={0.55}
            strokeWidth={width}
            fill="none"
          />
        );
      })}
      {sources.map((name) => (
        <text key={name} x={84} y={yOf(sources, name) + 4} fontSize={11} textAnchor="end" fill="#f2f2f2">
          {name.slice(0, 14)}
        </text>
      ))}
      {targets.map((name) => (
        <text key={name} x={236} y={yOf(targets, name) + 4} fontSize={11} fill="#f2f2f2">
          {name.slice(0, 14)}
        </text>
      ))}
    </svg>
  );
}

function WordCloud({ words }: { words: { text: string; count: number }[] }) {
  const max = words[0]?.count || 1;
  return (
    <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
      {words.map((word) => (
        <span
          key={word.text}
          className="text-ink"
          style={{ fontSize: 12 + (word.count / max) * 18, fontWeight: word.count > max / 2 ? 600 : 450 }}
        >
          {word.text}
        </span>
      ))}
    </div>
  );
}

function PinMap({ pins }: { pins: { name: string; lat: number; lon: number }[] }) {
  if (!pins.length) return <p className="text-sm text-mute">No coordinates on these rows.</p>;
  return (
    <MapContainer center={[pins[0].lat, pins[0].lon]} zoom={10} scrollWheelZoom={false} className="h-52 w-full">
      <MapReady />
      <TileLayer attribution="&copy; OpenStreetMap" url={OSM_TILES} />
      {pins.map((pin) => (
        <CircleMarker
          key={`${pin.name}-${pin.lat}`}
          center={[pin.lat, pin.lon]}
          radius={8}
          pathOptions={wellMarker}
        >
          <Popup>{pin.name}</Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}

function DetailTable({ title, rows }: { title: string; rows: Row[] }) {
  const cols = Object.keys(rows[0] || {}).filter((key) => typeof rows[0][key] !== "object").slice(0, 8);
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--fs-border)] bg-paper">
      <div className="flex items-center justify-between border-b border-[var(--fs-border)] px-3 py-2">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        <span className="text-xs text-mute">{rows.length} rows</span>
      </div>
      <div className="max-h-80 overflow-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-paper">
            <tr className="border-b border-[var(--fs-border)] text-[11px] uppercase tracking-wide text-mute">
              {cols.map((col) => (
                <th key={col} className="whitespace-nowrap px-3 py-2 font-semibold">
                  {label(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-b border-[var(--fs-border)] last:border-0">
                {cols.map((col) => (
                  <td key={col} className="max-w-[240px] truncate px-3 py-2 text-ink/80">
                    {row[col] == null || row[col] === "" ? "—" : String(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
