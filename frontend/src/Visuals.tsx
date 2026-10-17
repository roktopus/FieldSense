import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import type { Answer } from "./api";
import {
  IconAlert,
  IconCalendar,
  IconChart,
  IconCheck,
  IconEvidence,
  IconHeat,
  IconInfo,
  IconMap,
  IconTable,
  IconThermometer,
  IconTrend,
  IconUser,
  IconWell,
  IconX,
} from "./icons";

type Props = {
  answer: Answer;
  onOpenEvidence: () => void;
};

const COL_LABELS: Record<string, string> = {
  asset_id: "Well",
  well_type: "Type",
  delta_c: "ΔT (°C)",
  recorded_status: "Recorded",
  recorded_status_stale: "Stale?",
  reason: "Why",
  inspector_observation: "Inspector notes",
  downtime_days: "Downtime (days)",
  status: "Status",
  lat: "Lat",
  lon: "Lon",
  events: "Events",
  area_name: "Area",
  total: "Total",
  inspection_id: "Inspection",
  inspector_name: "Inspector",
};

function labelCol(key: string): string {
  if (COL_LABELS[key]) return COL_LABELS[key];
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function StatusBadge({ status }: { status?: string }) {
  const s = (status || "").toLowerCase().replace(/\s+/g, "_");
  if (s === "producing") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-200/80">
        <IconCheck size={14} className="text-emerald-600" />
        Producing
      </span>
    );
  }
  if (s === "not_producing") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-800 ring-1 ring-rose-200/80">
        <IconX size={14} className="text-rose-600" />
        Not producing
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
      <IconInfo size={14} />
      {status || "Unknown"}
    </span>
  );
}

function Panel({
  icon,
  title,
  meta,
  children,
}: {
  icon: ReactNode;
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200/90 bg-gradient-to-b from-white to-slate-50/80 shadow-[0_1px_0_rgba(15,23,42,0.04)]">
      <div className="flex items-center gap-2.5 border-b border-slate-100 bg-white/90 px-4 py-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-50 text-accent">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-[15px] font-semibold tracking-tight text-ink">{title}</h3>
        </div>
        {meta ? <div className="shrink-0 text-xs text-slate-500">{meta}</div> : null}
      </div>
      <div className="p-3 sm:p-4">{children}</div>
    </div>
  );
}

export function VisualRenderer({ answer, onOpenEvidence }: Props) {
  const visuals = answer.visuals || [];
  if (!visuals.length && answer.rows) {
    return (
      <div className="mt-3 space-y-3">
        <DataTable rows={answer.rows as Record<string, unknown>[]} />
        <AnswerFooter answer={answer} onOpenEvidence={onOpenEvidence} />
      </div>
    );
  }
  return (
    <div className="mt-3 space-y-3">
      {visuals.map((v, idx) => {
        const kind = String(v.kind || "");
        if (kind === "status_card") return <StatusCard key={idx} answer={answer} />;
        if (kind === "table")
          return (
            <DataTable
              key={idx}
              title={String(v.title || "Results")}
              rows={(answer.rows as Record<string, unknown>[]) || []}
              fields={(v.fields as string[] | undefined) || undefined}
            />
          );
        if (kind === "bar_chart")
          return (
            <BarBlock
              key={idx}
              title={String(v.title || "Comparison")}
              rows={(answer.rows as Record<string, unknown>[]) || []}
            />
          );
        if (kind === "line_chart")
          return (
            <LineBlock
              key={idx}
              title={String(v.title || "Trend")}
              rows={(answer.rows as Record<string, unknown>[]) || []}
            />
          );
        if (kind === "map")
          return <MapBlock key={idx} pins={(answer.rows as Record<string, unknown>[]) || []} />;
        if (kind === "heatmap")
          return <HeatmapBlock key={idx} rows={(answer.rows as Record<string, unknown>[]) || []} />;
        if (kind === "well_picker")
          return null; // summary already explains private-memory miss — no duplicate coaching panel
        return null;
      })}
      {(answer.conflicts as unknown[] | undefined)?.length ? (
        <div className="flex gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
          <IconAlert className="mt-0.5 shrink-0 text-amber-700" />
          <div>
            <div className="font-semibold text-amber-900">Conflicts disclosed</div>
            <ul className="mt-1 list-inside list-disc text-xs text-amber-950">
              {(answer.conflicts as Array<Record<string, unknown>>).map((c, i) => (
                <li key={i}>{String(c.message || c.type || JSON.stringify(c))}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      <AnswerFooter answer={answer} onOpenEvidence={onOpenEvidence} />
    </div>
  );
}

function AnswerFooter({ answer, onOpenEvidence }: Props) {
  const scope = answer.scope || {};
  const scopeBits = Object.entries(scope)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => ({ k: labelCol(k), v: String(v) }));

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {(answer.citations || []).slice(0, 6).map((c, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-1 text-xs font-medium text-sky-900 ring-1 ring-sky-100"
          >
            <IconEvidence size={12} className="text-sky-600" />
            {c.label || c.id}
          </span>
        ))}
        {answer.result_set_id ? (
          <button
            type="button"
            onClick={onOpenEvidence}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-accent/10 px-3 py-1.5 text-sm font-semibold text-accent transition hover:bg-accent/15"
          >
            <IconEvidence size={16} />
            View evidence
          </button>
        ) : null}
      </div>
      {scopeBits.length ? (
        <div className="flex flex-wrap gap-1.5 text-xs text-slate-500">
          {scopeBits.map(({ k, v }) => (
            <span key={k} className="rounded-md bg-slate-100/80 px-2 py-1">
              <span className="text-slate-400">{k}</span>{" "}
              <span className="font-medium text-slate-600">{v.length > 40 ? `${v.slice(0, 40)}…` : v}</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StatusCard({ answer }: { answer: Answer }) {
  const data = (answer.data || {}) as Record<string, any>;
  const li = data.latest_inspection || {};
  const notProd = String(data.status || "").includes("not");

  return (
    <Panel
      icon={<IconWell size={18} />}
      title={String(data.asset_id || "Well")}
      meta={<StatusBadge status={data.status} />}
    >
      <p className="mb-4 flex items-start gap-2 text-sm text-slate-600">
        <IconInfo size={16} className="mt-0.5 shrink-0 text-slate-400" />
        Based on the latest inspection — not live telemetry.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div
          className={`rounded-xl p-3 ring-1 ${
            notProd ? "bg-rose-50/80 ring-rose-100" : "bg-emerald-50/80 ring-emerald-100"
          }`}
        >
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
            <IconThermometer size={14} />
            ΔT (wellhead vs air)
          </div>
          <div className="mt-1 font-display text-3xl font-semibold tracking-tight text-ink">
            {data.delta_c ?? "—"}
            <span className="ml-1 text-base font-normal text-slate-500">°C</span>
          </div>
          <div className="mt-1 text-xs text-slate-500">Threshold {data.threshold_c ?? "—"} °C</div>
        </div>

        <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">
            <IconCalendar size={14} />
            Last inspection
          </div>
          <div className="mt-2 space-y-1.5 text-sm">
            <div className="font-medium text-ink">{String(li.inspected_at || "").slice(0, 10) || "—"}</div>
            <div className="flex items-center gap-1.5 text-slate-600">
              <IconUser size={14} className="text-slate-400" />
              {li.inspector_name || li.inspector_user_id || "—"}
            </div>
            <div className="text-slate-500">Method · {li.method || "—"}</div>
            <div className="font-mono text-xs text-sky-700">{li.inspection_id}</div>
          </div>
        </div>

        <div className="space-y-2">
          {data.recorded_status_stale ? (
            <div className="flex gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-950 ring-1 ring-amber-200">
              <IconAlert size={16} className="mt-0.5 shrink-0 text-amber-600" />
              <div>
                <div className="font-semibold">Recorded status stale</div>
                <div className="text-amber-900/90">{data.recorded_status}</div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl bg-slate-50 p-3 text-sm ring-1 ring-slate-200">
              Recorded · {data.recorded_status || "—"}
            </div>
          )}
          {(data.context_notes || []).slice(0, 1).map((n: any) => (
            <div key={n.note_id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Context</div>
              <p className="mt-1 leading-relaxed text-slate-700">{n.text}</p>
              <div className="mt-2 font-mono text-[11px] text-sky-700">{n.note_id}</div>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function DataTable({
  title,
  rows,
  fields,
}: {
  title?: string;
  rows: Record<string, unknown>[];
  fields?: string[];
}) {
  if (!rows?.length) {
    return (
      <Panel icon={<IconTable size={18} />} title={title || "Results"}>
        <div className="flex items-center gap-2 py-6 text-sm text-slate-500">
          <IconInfo size={16} />
          No matching wells for this query.
        </div>
      </Panel>
    );
  }

  const preferred = fields?.filter((f) => f in rows[0] && typeof rows[0][f] !== "object");
  const cols =
    preferred && preferred.length
      ? preferred
      : Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== "object");

  return (
    <Panel
      icon={<IconTable size={18} />}
      title={title || "Results"}
      meta={
        <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 font-medium text-slate-600">
          {rows.length} {rows.length === 1 ? "row" : "rows"}
        </span>
      }
    >
      <div className="-mx-1 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wide text-slate-500">
              {cols.map((c) => (
                <th key={c} className="whitespace-nowrap px-3 py-2 font-semibold" scope="col">
                  {labelCol(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={i}
                className="border-b border-slate-100/80 transition-colors last:border-0 hover:bg-teal-50/40"
              >
                {cols.map((c) => (
                  <td key={c} className="px-3 py-2.5 align-top">
                    <CellView col={c} value={r[c]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function CellView({ col, value }: { col: string; value: unknown }) {
  if (col === "asset_id") {
    return (
      <span className="inline-flex items-center gap-1.5 font-mono text-[13px] font-semibold text-ink">
        <IconWell size={14} className="text-accent" />
        {String(value)}
      </span>
    );
  }
  if (col === "status" || col === "recorded_status") {
    return <StatusBadge status={String(value ?? "")} />;
  }
  if (col === "recorded_status_stale") {
    return value ? (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700">
        <IconAlert size={12} /> Yes
      </span>
    ) : (
      <span className="text-xs text-slate-400">No</span>
    );
  }
  if (col === "delta_c" && typeof value === "number") {
    const hot = value < 15;
    return (
      <span className={`font-semibold tabular-nums ${hot ? "text-rose-700" : "text-emerald-700"}`}>
        {value.toFixed(1)}
      </span>
    );
  }
  if (col === "downtime_days" && typeof value === "number") {
    return <span className="font-semibold tabular-nums text-ink">{value}</span>;
  }
  if (col === "reason" || col === "inspector_observation") {
    const text = value == null || value === "" ? "—" : String(value);
    return (
      <span className="block max-w-[280px] leading-snug text-slate-700" title={text}>
        {text}
      </span>
    );
  }
  if (col === "well_type") {
    return (
      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
        {String(value ?? "—")}
      </span>
    );
  }
  return <span className="text-slate-700">{formatCell(value)}</span>;
}

function formatCell(v: unknown): string {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

const BAR_COLORS = ["#0f766e", "#0e7490", "#0369a1", "#1d4ed8", "#4338ca"];

function BarBlock({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  const data = rows.map((r) => ({
    name: String(r.asset_id),
    days: Number(r.downtime_days || 0),
    type: String(r.well_type || ""),
  }));
  return (
    <div className="space-y-3">
      <Panel
        icon={<IconChart size={18} />}
        title={title}
        meta={<span className="tabular-nums">{data.length} wells</span>}
      >
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
              <XAxis type="number" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                type="category"
                dataKey="name"
                width={88}
                tick={{ fill: "#334155", fontSize: 11, fontFamily: "ui-monospace, monospace" }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  borderRadius: 10,
                  border: "1px solid #e2e8f0",
                  boxShadow: "none",
                  fontSize: 12,
                }}
              />
              <Bar dataKey="days" name="Downtime (days)" radius={[0, 6, 6, 0]} barSize={18}>
                {data.map((_, i) => (
                  <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>
      <DataTable title="Ranked detail" rows={rows} />
    </div>
  );
}

function LineBlock({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  const data = rows.map((r) => {
    const offline = r.status === "not_producing";
    return {
      t: String(r.inspected_at).slice(0, 10),
      wellhead: r.wellhead_temp_c as number,
      ambient: r.ambient_temp_c as number,
      status: r.status,
      offlineMark: offline ? (r.wellhead_temp_c as number) : null,
    };
  });
  const offline = data.filter((d) => d.status === "not_producing").map((d) => d.t);
  return (
    <Panel
      icon={<IconTrend size={18} />}
      title={title}
      meta={
        offline.length ? (
          <span className="inline-flex items-center gap-1 text-rose-700">
            <IconX size={12} />
            {offline.length} offline
          </span>
        ) : undefined
      }
    >
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="t" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis unit="°C" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{
                borderRadius: 10,
                border: "1px solid #e2e8f0",
                boxShadow: "none",
                fontSize: 12,
              }}
              formatter={(value: number, name: string) => {
                if (name === "Not producing") return [value, name];
                return [value, name];
              }}
            />
            <Legend />
            <Line type="monotone" dataKey="wellhead" stroke="#0369a1" strokeWidth={2} name="Wellhead" dot={{ r: 3 }} />
            <Line type="monotone" dataKey="ambient" stroke="#94a3b8" strokeWidth={2} name="Ambient" dot={false} />
            <Line
              type="monotone"
              dataKey="offlineMark"
              stroke="#e11d48"
              strokeWidth={0}
              name="Not producing"
              connectNulls={false}
              dot={{ r: 6, fill: "#e11d48", stroke: "#fff", strokeWidth: 2 }}
              activeDot={{ r: 7 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 flex items-start gap-2 rounded-lg bg-rose-50/80 px-3 py-2 text-xs text-rose-900 ring-1 ring-rose-100">
        <IconX size={14} className="mt-0.5 shrink-0 text-rose-500" />
        <span>
          Marked not producing:{" "}
          <span className="font-semibold">{offline.length ? offline.join(", ") : "none in series"}</span>
        </span>
      </div>
    </Panel>
  );
}

function MapBlock({ pins }: { pins: Record<string, unknown>[] }) {
  if (!pins.length) {
    return (
      <Panel icon={<IconMap size={18} />} title="Map">
        <p className="text-sm text-slate-500">No map points.</p>
      </Panel>
    );
  }
  const lat = Number(pins[0].lat);
  const lon = Number(pins[0].lon);
  return (
    <div className="space-y-3">
      <Panel icon={<IconMap size={18} />} title="Spill map" meta={`${pins.length} wells`}>
        <MapContainer center={[lat, lon]} zoom={11} scrollWheelZoom={false}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {pins.map((p) => (
            <Marker key={String(p.asset_id)} position={[Number(p.lat), Number(p.lon)]}>
              <Popup>
                <strong className="font-mono">{String(p.asset_id)}</strong>
                <div className="mt-1 text-xs text-slate-600">
                  {Array.isArray(p.events) ? `${(p.events as unknown[]).length} event(s)` : ""}
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </Panel>
      <DataTable
        title="Locations"
        rows={pins.map((p) => ({
          asset_id: p.asset_id,
          lat: p.lat,
          lon: p.lon,
          events: Array.isArray(p.events) ? (p.events as unknown[]).length : 0,
        }))}
      />
    </div>
  );
}

function HeatmapBlock({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const months = (rows[0].months as string[]) || [];
  const max = Math.max(...rows.flatMap((r) => (r.values as number[]) || [0]), 1);
  return (
    <Panel icon={<IconHeat size={18} />} title="Spill heatmap" meta="Corrected detections excluded">
      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-slate-500">
              <th className="p-2 text-left font-semibold">Area</th>
              {months.map((m) => (
                <th key={m} className="p-2 font-semibold">
                  {m.slice(5)}
                </th>
              ))}
              <th className="p-2 font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={String(r.area_name)} className="border-t border-slate-100">
                <td className="p-2 font-medium text-ink">{String(r.area_name)}</td>
                {((r.values as number[]) || []).map((v, i) => {
                  const alpha = v === 0 ? 0.04 : 0.12 + (v / max) * 0.88;
                  return (
                    <td
                      key={i}
                      className="p-2 text-center tabular-nums"
                      style={{
                        background: `rgba(15,118,110,${alpha})`,
                        color: alpha > 0.55 ? "#fff" : "#0f172a",
                        borderRadius: 4,
                      }}
                    >
                      {v}
                    </td>
                  );
                })}
                <td className="p-2 text-center font-semibold tabular-nums">{String(r.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
