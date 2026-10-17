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
  mean_delta_c: "Avg ΔT (°C)",
  recorded_status: "Recorded status",
  recorded_status_stale: "Out of date?",
  reason: "Why",
  inspector_observation: "Inspector notes",
  downtime_days: "Downtime (days)",
  status: "Status",
  status_now: "Status now",
  lat: "Latitude",
  lon: "Longitude",
  events: "Events",
  area_name: "Area",
  total: "Total",
  inspection_id: "Inspection",
  inspector_name: "Inspector",
  reported_at: "Reported",
  response: "Response",
  hours_to_response: "Hours to respond",
  deadline_hours: "Deadline (hours)",
  met: "Met deadline?",
  bypass_in: "Bypass in",
  bypass_out: "Bypass out",
  approval: "Approval",
  volume_bbl: "Volume (bbl)",
  cleanup_job: "Cleanup job",
  compliant: "Compliant?",
  latest_inspection: "Latest inspection",
  latest_operator_note: "Latest operator note",
  rank: "Rank",
  operator_note_evidence: "Operator note",
  last_repair: "Last repair",
  lot: "Lot",
  provenance: "How we know",
  share_pct: "Share (%)",
  typical_extra_days: "Typical extra days",
  inspection: "Inspection",
};

function labelCol(key: string): string {
  if (COL_LABELS[key]) return COL_LABELS[key];
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function friendlyMissing(fields: string[]): string {
  const map: Record<string, string> = {
    reservoir_pressure: "reservoir pressure",
    tubing_pressure: "tubing pressure",
    casing_pressure: "casing pressure",
    oil_volume_bbl: "oil volume (barrels)",
    bopd: "barrels per day",
    cumulative_production: "cumulative production",
  };
  return fields.map((f) => map[f] || f.replace(/_/g, " ")).join(", ");
}

function StatusBadge({ status }: { status?: string }) {
  const s = (status || "").toLowerCase().replace(/\s+/g, "_");
  if (s === "producing") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-moss-soft px-2 py-1 text-xs font-semibold text-[var(--fs-ok)] ring-1 ring-moss/20">
        <IconCheck size={14} className="text-moss" />
        Producing
      </span>
    );
  }
  if (s === "not_producing") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-rose-50 px-2 py-1 text-xs font-semibold text-[var(--fs-danger)] ring-1 ring-rose-200/80">
        <IconX size={14} className="text-[var(--fs-danger)]" />
        Not producing
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-stone px-2 py-1 text-xs font-semibold text-mute ring-1 ring-[var(--fs-border)]">
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
    <div className="overflow-hidden rounded-[14px] border border-[var(--fs-border)] bg-white shadow-soft">
      <div className="flex items-center gap-2.5 border-b border-[var(--fs-border)] bg-paper/90 px-4 py-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-moss-soft text-moss">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-[15px] font-semibold tracking-tight text-ink">
            {title}
          </h3>
        </div>
        {meta ? <div className="shrink-0 text-xs text-mute">{meta}</div> : null}
      </div>
      <div className="p-3 sm:p-4">{children}</div>
    </div>
  );
}

export function VisualRenderer({ answer, onOpenEvidence }: Props) {
  const visuals = answer.visuals || [];
  const rows = (answer.rows as Record<string, unknown>[] | undefined) || [];
  const unsupported = answer.coverage?.status === "unsupported";
  const shortOnly =
    unsupported ||
    answer.kind === "short_answer" ||
    (String(answer.kind || "") === "" && !visuals.length && rows.length === 0);

  // Empty [] is truthy in JS — only fall back to a table when there are real rows.
  if (!visuals.length && rows.length > 0 && !shortOnly) {
    return (
      <div className="mt-3 space-y-3">
        <DataTable rows={rows} />
        <AnswerFooter answer={answer} onOpenEvidence={onOpenEvidence} />
      </div>
    );
  }
  return (
    <div className="mt-3 space-y-3">
      {!shortOnly
        ? visuals.map((v, idx) => {
        const kind = String(v.kind || "");
        if (kind === "status_card") return <StatusCard key={idx} answer={answer} />;
        if (kind === "table") {
          if (!rows.length) return null;
          return (
            <DataTable
              key={idx}
              title={String(v.title || "Matching wells")}
              rows={rows}
              fields={(v.fields as string[] | undefined) || undefined}
            />
          );
        }
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
        if (kind === "stacked_bar")
          return (
            <StackedBarBlock
              key={idx}
              title={String(v.title || "Stacked comparison")}
              rows={
                ((answer.data?.stacked as Record<string, unknown>[]) ||
                  (answer.rows as Record<string, unknown>[]) ||
                  []) as Record<string, unknown>[]
              }
              fields={(v.fields as string[] | undefined) || undefined}
            />
          );
        if (kind === "well_picker")
          return null; // summary already explains private-memory miss — no duplicate coaching panel
        return null;
      })
        : null}
      {unsupported ? (
        <div className="flex gap-3 rounded-[14px] border border-[var(--fs-border)] bg-stone/70 p-3.5 text-sm">
          <IconInfo className="mt-0.5 shrink-0 text-mute" />
          <div>
            <div className="font-semibold text-ink">We don&apos;t have this data</div>
            <p className="mt-1 text-xs leading-relaxed text-mute">
              Missing:{" "}
              {Array.isArray(answer.coverage?.missing)
                ? friendlyMissing(answer.coverage!.missing as string[])
                : "see the summary above"}
              . No map or table is shown — inventing values would be dishonest.
            </p>
            {Array.isArray(answer.coverage?.searched) ? (
              <p className="mt-1 text-xs text-mute/80">
                Looked in:{" "}
                {(answer.coverage!.searched as string[])
                  .map((s) => s.replace(/_/g, " "))
                  .join(", ")}
                .
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
      {(answer.conflicts as unknown[] | undefined)?.length ? (
        <div className="flex gap-3 rounded-[14px] border border-amber-200 bg-amber-50/90 p-3.5 text-sm">
          <IconAlert className="mt-0.5 shrink-0 text-[var(--fs-warn)]" />
          <div>
            <div className="font-semibold text-amber-950">Sources disagree</div>
            <ul className="mt-1 list-inside list-disc text-xs text-amber-950/90">
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
  const unsupported = answer.coverage?.status === "unsupported";
  const scopeBits = Object.entries(scope)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => ({ k: labelCol(k), v: String(v) }));
  // Coverage refusals store no linked evidence — don't tease an empty Sources drawer.
  // (Other answers may still open Sources; the API synthesizes from rows when needed.)
  const showSources = Boolean(answer.result_set_id) && !unsupported;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {(answer.citations || []).slice(0, 6).map((c, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-md bg-moss-soft px-2 py-1 text-xs font-medium text-moss ring-1 ring-moss/15"
          >
            <IconEvidence size={12} className="text-moss" />
            {c.label || c.id}
          </span>
        ))}
        {showSources ? (
          <button
            type="button"
            onClick={onOpenEvidence}
            className="ml-auto inline-flex items-center gap-1.5 rounded-[10px] bg-copper/10 px-3 py-1.5 text-sm font-semibold text-copper-deep transition hover:bg-copper/15"
          >
            <IconEvidence size={16} />
            See sources
          </button>
        ) : null}
      </div>
      {scopeBits.length ? (
        <div className="flex flex-wrap gap-1.5 text-xs text-mute">
          {scopeBits.map(({ k, v }) => (
            <span key={k} className="rounded-md bg-stone px-2 py-1">
              <span className="text-mute/70">{k}</span>{" "}
              <span className="font-medium text-ink/80">
                {v.length > 40 ? `${v.slice(0, 40)}…` : v}
              </span>
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
      <p className="mb-4 flex items-start gap-2 text-sm text-mute">
        <IconInfo size={16} className="mt-0.5 shrink-0 text-mute/70" />
        Based on the latest inspection — not live telemetry.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div
          className={`rounded-xl p-3 ring-1 ${
            notProd ? "bg-rose-50/80 ring-rose-100" : "bg-emerald-50/80 ring-emerald-100"
          }`}
        >
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-mute">
            <IconThermometer size={14} />
            ΔT (wellhead vs air)
          </div>
          <div className="mt-1 font-display text-3xl font-semibold tracking-tight text-ink">
            {data.delta_c ?? "—"}
            <span className="ml-1 text-base font-normal text-mute">°C</span>
          </div>
          <div className="mt-1 text-xs text-mute">Threshold {data.threshold_c ?? "—"} °C</div>
        </div>

        <div className="rounded-xl bg-white p-3 ring-1 ring-[var(--fs-border)]">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-mute">
            <IconCalendar size={14} />
            Last inspection
          </div>
          <div className="mt-2 space-y-1.5 text-sm">
            <div className="font-medium text-ink">{String(li.inspected_at || "").slice(0, 10) || "—"}</div>
            <div className="flex items-center gap-1.5 text-mute">
              <IconUser size={14} className="text-mute/70" />
              {li.inspector_name || li.inspector_user_id || "—"}
            </div>
            <div className="text-mute">Method · {li.method || "—"}</div>
            <div className="font-mono text-xs text-moss">{li.inspection_id}</div>
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
            <div className="rounded-xl bg-stone/60 p-3 text-sm ring-1 ring-[var(--fs-border)]">
              Recorded · {data.recorded_status || "—"}
            </div>
          )}
          {(data.context_notes || []).slice(0, 1).map((n: any) => (
            <div key={n.note_id} className="rounded-xl border border-[var(--fs-border)] bg-white p-3 text-sm">
              <div className="text-xs font-semibold uppercase tracking-wide text-mute/70">Context</div>
              <p className="mt-1 leading-relaxed text-ink/80">{n.text}</p>
              <div className="mt-2 font-mono text-[11px] text-moss">{n.note_id}</div>
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
      <Panel icon={<IconTable size={18} />} title={title || "Matching wells"}>
        <div className="flex items-center gap-2 py-6 text-sm text-mute">
          <IconInfo size={16} />
          Nothing matched this question.
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
      title={title || "Matching wells"}
      meta={
        <span className="inline-flex items-center gap-1 rounded-md bg-stone px-2 py-1 font-medium text-mute">
          {rows.length} {rows.length === 1 ? "row" : "rows"}
        </span>
      }
    >
      <div className="-mx-1 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--fs-border)] text-[11px] uppercase tracking-wide text-mute">
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
                className="border-b border-[var(--fs-border)] transition-colors last:border-0 hover:bg-moss-soft/50"
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
        <IconWell size={14} className="text-moss" />
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
      <span className="text-xs text-mute/70">No</span>
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
      <span className="block max-w-[280px] leading-snug text-ink/80" title={text}>
        {text}
      </span>
    );
  }
  if (col === "well_type") {
    return (
      <span className="rounded-md bg-stone px-2 py-0.5 text-xs font-medium text-ink/80">
        {String(value ?? "—")}
      </span>
    );
  }
  return <span className="text-ink/80">{formatCell(value)}</span>;
}

function formatCell(v: unknown): string {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

const BAR_COLORS = ["#1a7a6d", "#c46b2d", "#0b2420", "#5c6b64", "#9a5222"];

function BarBlock({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  const valueKey = rows[0]?.mean_delta_c != null ? "mean_delta_c" : "downtime_days";
  const labelKey = rows[0]?.area_name != null && rows[0]?.asset_id == null ? "area_name" : "asset_id";
  const data = rows.map((r) => ({
    name: String(r[labelKey] ?? r.asset_id ?? r.area_name ?? ""),
    value: Number(r[valueKey] ?? r.downtime_days ?? r.mean_delta_c ?? 0),
    type: String(r.well_type || ""),
  }));
  const seriesName = valueKey === "mean_delta_c" ? "Mean ΔT (°C)" : "Downtime (days)";
  return (
    <div className="space-y-3">
      <Panel
        icon={<IconChart size={18} />}
        title={title}
        meta={<span className="tabular-nums">{data.length} series</span>}
      >
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
              <XAxis type="number" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                type="category"
                dataKey="name"
                width={120}
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
              <Bar dataKey="value" name={seriesName} radius={[0, 6, 6, 0]} barSize={18}>
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

function StackedBarBlock({
  title,
  rows,
  fields,
}: {
  title: string;
  rows: Record<string, unknown>[];
  fields?: string[];
}) {
  const stackKeys =
    fields?.filter((f) => f !== "area_name") ||
    ["parts", "crews", "contractors", "weather"].filter((k) =>
      rows.some((r) => r[k] != null),
    );
  const data = rows.map((r) => {
    const row: Record<string, string | number> = { name: String(r.area_name || r.asset_id || "") };
    for (const k of stackKeys) row[k] = Number(r[k] || 0);
    return row;
  });
  return (
    <Panel icon={<IconChart size={18} />} title={title} meta={<span className="tabular-nums">{data.length} areas</span>}>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ left: 8, right: 16, top: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={60} />
            <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
            <Tooltip />
            <Legend />
            {stackKeys.map((k, i) => (
              <Bar key={k} dataKey={k} stackId="a" fill={BAR_COLORS[i % BAR_COLORS.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
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
            <Line type="monotone" dataKey="wellhead" stroke="#1a7a6d" strokeWidth={2} name="Wellhead" dot={{ r: 3 }} />
            <Line type="monotone" dataKey="ambient" stroke="#5c6b64" strokeWidth={2} name="Ambient" dot={false} />
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
        <p className="text-sm text-mute">No map points.</p>
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
                <div className="mt-1 text-xs text-mute">
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
            <tr className="text-[11px] uppercase tracking-wide text-mute">
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
              <tr key={String(r.area_name)} className="border-t border-[var(--fs-border)]">
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
