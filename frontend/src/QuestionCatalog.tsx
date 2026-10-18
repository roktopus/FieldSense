import { useState } from "react";
import {
  CatalogQuestion,
  CatalogTurn,
  FIELDSENSE_QUESTIONS,
  HOST_QUESTIONS,
  PromptSource,
} from "./promptCatalog";
import { IconSpark } from "./icons";

type Props = {
  onAskTurn: (turn: CatalogTurn, question: CatalogQuestion) => void;
  disabled?: boolean;
};

export function QuestionCatalog({ onAskTurn, disabled }: Props) {
  const [tab, setTab] = useState<PromptSource>("host");
  const [expanded, setExpanded] = useState<string | null>(null);

  const items = tab === "host" ? HOST_QUESTIONS : FIELDSENSE_QUESTIONS;

  return (
    <div className="w-full">
      <div
        className="flex flex-col gap-2 rounded-lg border border-[var(--fs-border)] bg-stone p-1.5"
        role="tablist"
        aria-label="Question catalogs"
      >
        <CatalogTab
          active={tab === "host"}
          onClick={() => setTab("host")}
          badge="HOST"
          badgeClass="bg-white text-black"
          title="Official test-data questions"
          subtitle="Q1–Q11 from the FlytBase test-data set · answer as of 15 Jan 2027"
          accent="copper"
        />
        <CatalogTab
          active={tab === "fieldsense"}
          onClick={() => setTab("fieldsense")}
          badge="OURS"
          badgeClass="border border-white/50 text-ink"
          title="FieldSense showcase"
          subtitle="Curated demos with rich tables and charts on the same test import"
          accent="moss"
        />
      </div>

      {tab === "host" ? (
        <p className="mt-3 text-xs leading-snug text-mute">
          Ask in order from <span className="font-medium text-ink">final-questions.md</span>. Multi-turn cards open in place.
        </p>
      ) : (
        <p className="mt-3 text-xs leading-snug text-mute">
          FieldSense demos on the same import. Use the host tab for the official set.
        </p>
      )}

      <ul className="mt-3 grid grid-cols-1 gap-2">
        {items.map((q) => {
          const open = expanded === q.id;
          const multi = q.turns.length > 1;
          return (
            <li
              key={q.id}
              className="overflow-hidden rounded-lg border border-ink/10 bg-paper transition duration-150 hover:border-ink/40"
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => {
                  if (multi) setExpanded(open ? null : q.id);
                  else onAskTurn(q.turns[0], q);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left disabled:opacity-50"
              >
                <span
                  className={`mt-0.5 flex h-9 w-9 shrink-0 flex-col items-center justify-center rounded-md text-[11px] font-semibold leading-none ${
                    q.source === "host"
                      ? "bg-white text-black"
                      : "border border-white/50 text-ink"
                  }`}
                >
                  {q.id}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-mute">
                    {q.source === "host" ? "Host" : "FieldSense"} · {q.tag}
                    {multi ? ` · ${q.turns.length} turns` : ` · ${q.turns[0].askerName}`}
                  </span>
                  <span className="mt-0.5 block truncate text-sm font-semibold text-ink">{q.title}</span>
                  <span className="mt-0.5 line-clamp-1 block text-xs text-mute">{q.blurb}</span>
                </span>
                <span className="flex shrink-0 flex-col items-end justify-center gap-1">
                  <span className="inline-flex items-center gap-1 rounded-md border border-ink/15 px-2.5 py-1.5 text-xs font-semibold text-ink">
                    <IconSpark size={12} />
                    {multi ? (open ? "Hide turns" : "Show turns") : "Ask"}
                  </span>
                </span>
              </button>

              {multi && open ? (
                <ol className="space-y-2 border-t border-[var(--fs-border)] bg-stone/40 px-4 py-3">
                  {q.turns.map((t, idx) => (
                    <li
                      key={t.id}
                      className="flex flex-col gap-2 rounded-md border border-[var(--fs-border)] bg-paper p-3 sm:flex-row sm:items-start"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                          <span className="font-bold text-ink">
                            Turn {idx + 1}
                          </span>
                          <span className="rounded-md bg-stone px-1.5 py-0.5 font-medium text-mute">
                            {t.askerName}
                          </span>
                          <span
                            className={`rounded-md px-1.5 py-0.5 font-semibold ${
                              t.session === "new"
                                ? "bg-copper-soft text-copper-deep"
                                : "bg-moss-soft text-moss"
                            }`}
                          >
                            {t.session === "new" ? "New session" : "Same session"}
                          </span>
                        </div>
                        <p className="mt-1.5 text-sm leading-relaxed text-ink/90">{t.text}</p>
                      </div>
                      <button
                        type="button"
                        disabled={disabled}
                        onClick={() => onAskTurn(t, q)}
                        className="shrink-0 rounded-md bg-white px-3 py-2 text-xs font-semibold text-black transition hover:bg-neutral-200 disabled:opacity-40"
                      >
                        Ask this turn
                      </button>
                    </li>
                  ))}
                </ol>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function CatalogTab({
  active,
  onClick,
  badge,
  badgeClass,
  title,
  subtitle,
  accent,
}: {
  active: boolean;
  onClick: () => void;
  badge: string;
  badgeClass: string;
  title: string;
  subtitle: string;
  accent: "copper" | "moss";
}) {
  const ring = active
    ? "border-white/30 bg-[#242424]"
    : "border-transparent hover:bg-white/5";

  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex flex-1 gap-3 rounded-lg border px-3.5 py-3 text-left transition duration-150 ${ring}`}
    >
      <span className={`mt-0.5 rounded-md px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${badgeClass}`}>
        {badge}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink">{title}</span>
        <span className="mt-0.5 block text-[11px] leading-snug text-mute">{subtitle}</span>
      </span>
    </button>
  );
}
