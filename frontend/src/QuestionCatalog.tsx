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
  const [expanded, setExpanded] = useState<string | null>("Q3");

  const items = tab === "host" ? HOST_QUESTIONS : FIELDSENSE_QUESTIONS;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <div
        className="flex flex-col gap-3 rounded-[16px] border border-[var(--fs-border)] bg-paper/90 p-3 shadow-soft sm:flex-row sm:items-stretch sm:p-2"
        role="tablist"
        aria-label="Question catalogs"
      >
        <CatalogTab
          active={tab === "host"}
          onClick={() => setTab("host")}
          badge="HOST"
          badgeClass="bg-copper text-white"
          title="Official test-data questions"
          subtitle="Q1–Q11 from the FlytBase test-data set · answer as of 15 Jan 2027"
          accent="copper"
        />
        <CatalogTab
          active={tab === "fieldsense"}
          onClick={() => setTab("fieldsense")}
          badge="OURS"
          badgeClass="bg-moss text-white"
          title="FieldSense showcase"
          subtitle="Curated demos with rich tables and charts on the same test import"
          accent="moss"
        />
      </div>

      {tab === "host" ? (
        <div className="mt-4 rounded-[14px] border border-copper/25 bg-copper-soft/40 px-4 py-3 text-sm text-ink">
          <p className="font-semibold text-copper-deep">Submit these to the host</p>
          <p className="mt-1 text-xs leading-relaxed text-mute">
            Run in order from{" "}
            <span className="font-medium text-ink">test-data/final-questions.md</span>. Multi-turn
            cards expand so you can ask each turn as the named person (new or same session). Save
            full answers and visuals for your write-up — not the sample-data Q1–Q18 set.
          </p>
        </div>
      ) : (
        <div className="mt-4 rounded-[14px] border border-moss/25 bg-moss-soft/50 px-4 py-3 text-sm text-ink">
          <p className="font-semibold text-moss">FieldSense extras</p>
          <p className="mt-1 text-xs leading-relaxed text-mute">
            Handy single-click demos. Prefer the{" "}
            <button
              type="button"
              className="font-semibold text-copper-deep underline-offset-2 hover:underline"
              onClick={() => setTab("host")}
            >
              Official test-data
            </button>{" "}
            tab when preparing host submission.
          </p>
        </div>
      )}

      <ul className="mt-4 space-y-2.5">
        {items.map((q) => {
          const open = expanded === q.id;
          const multi = q.turns.length > 1;
          return (
            <li
              key={q.id}
              className={`overflow-hidden rounded-[14px] border shadow-soft transition ${
                q.source === "host"
                  ? "border-copper/20 bg-paper"
                  : "border-moss/20 bg-paper"
              }`}
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => {
                  if (multi) setExpanded(open ? null : q.id);
                  else onAskTurn(q.turns[0], q);
                }}
                className="flex w-full gap-3 px-4 py-3.5 text-left disabled:opacity-50"
              >
                <span
                  className={`mt-0.5 flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-[10px] text-[11px] font-bold leading-none ${
                    q.source === "host"
                      ? "bg-copper text-white"
                      : "bg-moss text-white"
                  }`}
                >
                  {q.id}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] ${
                        q.source === "host"
                          ? "bg-copper-soft text-copper-deep"
                          : "bg-moss-soft text-moss"
                      }`}
                    >
                      {q.source === "host" ? "Host" : "FieldSense"} · {q.tag}
                    </span>
                    {multi ? (
                      <span className="text-[11px] font-medium text-mute">
                        {q.turns.length} turns
                      </span>
                    ) : (
                      <span className="text-[11px] text-mute">Ask as {q.turns[0].askerName}</span>
                    )}
                  </span>
                  <span className="mt-1 block font-semibold text-ink">{q.title}</span>
                  <span className="mt-0.5 block text-xs leading-relaxed text-mute">{q.blurb}</span>
                  {q.visualHint ? (
                    <span className="mt-1 block text-[11px] text-moss">Visual: {q.visualHint}</span>
                  ) : null}
                </span>
                <span className="flex shrink-0 flex-col items-end justify-center gap-1">
                  <span
                    className={`inline-flex items-center gap-1 rounded-[10px] px-2.5 py-1.5 text-xs font-semibold ${
                      q.source === "host"
                        ? "bg-copper/10 text-copper-deep"
                        : "bg-moss/10 text-moss"
                    }`}
                  >
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
                      className="flex flex-col gap-2 rounded-[12px] border border-[var(--fs-border)] bg-white p-3 sm:flex-row sm:items-start"
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
                        className="shrink-0 rounded-[10px] bg-copper px-3 py-2 text-xs font-semibold text-white transition hover:bg-copper-deep disabled:opacity-40"
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
  const ring =
    accent === "copper"
      ? active
        ? "border-copper/40 bg-copper-soft/50 ring-2 ring-copper/25"
        : "border-transparent hover:bg-stone/80"
      : active
        ? "border-moss/40 bg-moss-soft/60 ring-2 ring-moss/20"
        : "border-transparent hover:bg-stone/80";

  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex flex-1 gap-3 rounded-[12px] border px-3.5 py-3 text-left transition ${ring}`}
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
