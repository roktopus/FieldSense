import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Answer, User, api } from "./api";
import { FieldSenseLogo } from "./FieldSenseLogo";
import { IconEvidence, IconSend, IconUser, IconX } from "./icons";
import { WellsMark } from "./motion/WellsMark";
import { ParticleField } from "./motion/ParticleField";
import { WELLS } from "./persona";
import { QuestionCatalog } from "./QuestionCatalog";
import type { CatalogQuestion, CatalogTurn } from "./promptCatalog";
import { VisualRenderer } from "./Visuals";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer?: Answer;
};

type ScriptCue = {
  question: CatalogQuestion;
  nextTurn: CatalogTurn;
  nextIndex: number;
};

function friendlyImport(status: string, version: string | null | undefined): string {
  if (status === "none") return "No field data loaded yet — run make import-data";
  if (status === "succeeded" || status === "success") {
    return version ? `Data ready — ${version}` : "Data ready";
  }
  return version ? `Data ${status} — ${version}` : `Data ${status}`;
}

function friendlyRole(role: string): string {
  return role.replace(/_/g, " ");
}

export default function App() {
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserId] = useState<string>(() => localStorage.getItem("fieldsense_user") || "");
  const [conversations, setConversations] = useState<Array<{ id: string; title: string }>>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [areas, setAreas] = useState<Array<{ area_id: string; name: string }>>([]);
  const [evidence, setEvidence] = useState<Array<Record<string, unknown>> | null>(null);
  const [importInfo, setImportInfo] = useState<string>("Checking data…");
  const [asOf, setAsOf] = useState(
    () => localStorage.getItem("fieldsense_as_of") || "2027-01-15T00:00:00Z",
  );
  const [questionsOpen, setQuestionsOpen] = useState(false);
  const [scriptCue, setScriptCue] = useState<ScriptCue | null>(null);
  const skipUserResetRef = useRef(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const activeUser = useMemo(() => users.find((u) => u.user_id === userId), [users, userId]);

  useEffect(() => {
    api.users().then((r) => setUsers(r.users)).catch((e) => setError(String(e)));
    api.areas().then((r) => setAreas(r.areas)).catch(() => undefined);
    api.importLatest().then((r) => {
      setImportInfo(friendlyImport(r.status, r.dataset_version));
      const serverClock = typeof r.evaluation_as_of === "string" ? r.evaluation_as_of : null;
      if (serverClock) {
        const stored = localStorage.getItem("fieldsense_as_of");
        const needsSync =
          !stored ||
          (String(r.dataset_version || "").startsWith("test") && stored < "2027-01-01") ||
          (String(r.dataset_version || "").startsWith("sample") && stored >= "2027-01-01");
        if (needsSync) {
          setAsOf(serverClock);
          localStorage.setItem("fieldsense_as_of", serverClock);
        }
      }
    });
  }, []);

  useEffect(() => {
    localStorage.setItem("fieldsense_as_of", asOf);
  }, [asOf]);

  useEffect(() => {
    if (!userId) return;
    localStorage.setItem("fieldsense_user", userId);
    api
      .selectUser(userId)
      .then(() => api.conversations(userId))
      .then((r) => setConversations(r.conversations))
      .catch((e) => setError(String(e)));
    if (skipUserResetRef.current) {
      skipUserResetRef.current = false;
      return;
    }
    setConversationId(null);
    setMessages([]);
    setEvidence(null);
    setQuestionsOpen(false);
    setScriptCue(null);
  }, [userId]);

  function goHome() {
    setConversationId(null);
    setMessages([]);
    setEvidence(null);
    setQuestionsOpen(false);
    setScriptCue(null);
    setError(null);
    setInput("");
  }

  async function newChat() {
    if (!userId) return;
    const c = await api.createConversation(userId);
    setConversationId(c.id);
    setMessages([]);
    setEvidence(null);
    setQuestionsOpen(false);
    setScriptCue(null);
    const list = await api.conversations(userId);
    setConversations(list.conversations);
  }

  async function openChat(id: string) {
    if (!userId) return;
    setConversationId(id);
    setQuestionsOpen(false);
    setScriptCue(null);
    const c = await api.getConversation(userId, id);
    setMessages(
      c.messages.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
        answer: m.answer,
      })),
    );
  }

  async function runMessage(
    uid: string,
    text: string,
    opts: { newSession: boolean; reuseConversationId?: string | null },
  ) {
    setError(null);
    setLoading(true);
    setQuestionsOpen(false);
    try {
      await api.selectUser(uid);
      let cid = opts.newSession ? null : opts.reuseConversationId ?? null;
      if (!cid) {
        const c = await api.createConversation(uid, text.slice(0, 60));
        cid = c.id;
      }
      setConversationId(cid);
      if (opts.newSession) {
        setMessages([{ id: crypto.randomUUID(), role: "user", content: text }]);
      } else {
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: text }]);
      }
      setInput("");
      const res = await api.run(uid, cid, text);
      setMessages((prev) => [
        ...prev,
        {
          id: res.run_id,
          role: "assistant",
          content: res.answer?.summary || "Done.",
          answer: res.answer,
        },
      ]);
      const list = await api.conversations(uid);
      setConversations(list.conversations);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function send(text: string) {
    if (!userId || !text.trim()) return;
    await runMessage(userId, text, {
      newSession: !conversationId,
      reuseConversationId: conversationId,
    });
    setScriptCue(null);
  }

  async function askCatalogTurn(turn: CatalogTurn, question: CatalogQuestion) {
    const switching = turn.userId !== userId;
    if (switching) {
      skipUserResetRef.current = true;
      setUserId(turn.userId);
    }

    const sameSession =
      turn.session === "same" && !switching && Boolean(conversationId) && messages.length > 0;

    await runMessage(turn.userId, turn.text, {
      newSession: !sameSession,
      reuseConversationId: sameSession ? conversationId : null,
    });

    const idx = question.turns.findIndex((t) => t.id === turn.id);
    const next = idx >= 0 ? question.turns[idx + 1] : undefined;
    if (next) {
      setScriptCue({ question, nextTurn: next, nextIndex: idx + 1 });
    } else {
      setScriptCue(null);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  async function openEvidence(answer?: Answer) {
    if (!userId || !answer?.result_set_id) return;
    try {
      const r = await api.evidence(userId, answer.result_set_id);
      setEvidence(r.items?.length ? r.items : []);
    } catch (e) {
      setError(String(e));
      setEvidence([]);
    }
  }

  useEffect(() => {
    const pane = scrollerRef.current;
    if (!pane || !messages.length) return;
    pane.scrollTop = pane.scrollHeight;
  }, [messages, loading]);

  function mentionArea(name: string) {
    setInput((prev) => {
      if (prev.includes(name)) return prev;
      if (!prev.trim()) return `In ${name}, `;
      return `${prev.trim()} — ${name}. `;
    });
    inputRef.current?.focus();
  }

  return (
    <div className="flex h-dvh overflow-hidden font-body text-ink">
      <aside className="fs-sidebar flex h-full w-[272px] shrink-0 flex-col overflow-hidden border-r border-white/10 text-white">
        <div className="border-b border-white/10 px-4 py-4">
          <button
            type="button"
            onClick={goHome}
            className="group w-full rounded-[12px] px-1 py-1 text-left transition hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-copper"
            aria-label="FieldSense home"
            title="Home"
          >
            <FieldSenseLogo className="transition group-hover:opacity-95" />
          </button>
        </div>
        <div className="space-y-2 p-3">
          <button
            type="button"
            onClick={() => void newChat()}
            disabled={!userId}
            className="w-full rounded-lg bg-white px-3 py-2.5 text-sm font-semibold text-black transition hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            New conversation
          </button>
        </div>
        <LeasePlat areas={areas} onPick={mentionArea} />
        <div className="px-4 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/60">
          Recent questions
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-1">
          {conversations.length === 0 ? (
            <p className="px-2 py-3 text-xs leading-relaxed text-white/60">
              Your questions will show up here.
            </p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => void openChat(c.id)}
                className={`mb-0.5 w-full rounded-[10px] px-3 py-2.5 text-left text-sm leading-snug transition ${
                  conversationId === c.id
                    ? "bg-white/12 text-white"
                    : "text-white/75 hover:bg-white/8 hover:text-white"
                }`}
              >
                {c.title}
              </button>
            ))
          )}
        </div>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-[var(--fs-border)] bg-paper px-5 py-3">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-mute">Who&apos;s asking</span>
            <select
              className="rounded-md border border-[var(--fs-border)] bg-paper px-2.5 py-1.5 text-ink"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            >
              <option value="">Choose…</option>
              {users.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.name} · {friendlyRole(u.role)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-mute">Answer as of</span>
            <input
              className="rounded-md border border-[var(--fs-border)] bg-paper px-2.5 py-1.5 font-mono text-xs text-ink"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
              aria-label="Analysis date and time"
            />
          </label>
          <div className="text-xs font-medium text-moss">{importInfo}</div>
          {activeUser ? (
            <div className="ml-auto text-xs text-mute">
              Signed in as <span className="font-semibold text-ink">{activeUser.name}</span>
              <span className="mx-1.5 text-stone">·</span>
              <span className="text-copper-deep">Demo only — not real sign-in</span>
            </div>
          ) : (
            <div className="ml-auto text-xs text-copper-deep">Demo only — not real sign-in</div>
          )}
        </header>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <section className="relative flex min-h-0 min-w-0 flex-1 flex-col">
            <ParticleField />
            <div
              ref={scrollerRef}
              className={
                messages.length
                  ? "relative z-10 min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-6"
                  : "relative z-10 flex min-h-0 flex-1 items-center justify-center overflow-hidden px-6"
              }
            >
              {!messages.length ? (
                <WellsHero signedIn={Boolean(userId)} />
              ) : (
                <>
                  {scriptCue ? (
                    <div className="mx-auto flex w-full max-w-4xl flex-col gap-2 rounded-[14px] border border-copper/30 bg-copper-soft/50 px-4 py-3 sm:flex-row sm:items-center">
                      <div className="min-w-0 flex-1 text-sm">
                        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-copper-deep">
                          Host script · {scriptCue.question.id} · next turn{" "}
                          {scriptCue.nextIndex + 1}/{scriptCue.question.turns.length}
                        </div>
                        <p className="mt-1 text-xs text-mute">
                          Ask as <span className="font-semibold text-ink">{scriptCue.nextTurn.askerName}</span>
                          {" · "}
                          {scriptCue.nextTurn.session === "new" ? "new session" : "same session"}
                        </p>
                        <p className="mt-1 line-clamp-2 text-sm text-ink">{scriptCue.nextTurn.text}</p>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          disabled={loading}
                          onClick={() => void askCatalogTurn(scriptCue.nextTurn, scriptCue.question)}
                          className="rounded-md bg-white px-3 py-2 text-xs font-semibold text-black hover:bg-neutral-200 disabled:opacity-40"
                        >
                          Ask next turn
                        </button>
                        <button
                          type="button"
                          onClick={() => setScriptCue(null)}
                          className="rounded-[10px] px-3 py-2 text-xs font-medium text-mute hover:bg-white/60"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {messages.map((m) =>
                    m.role === "user" ? (
                      <div key={m.id} className="animate-fs-enter flex justify-end gap-2.5">
                        <div className="max-w-2xl rounded-md bg-white/8 px-4 py-3 text-sm leading-relaxed text-ink ring-1 ring-white/10">
                          {m.content}
                        </div>
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-black">
                          <IconUser size={16} />
                        </div>
                      </div>
                    ) : (
                      <div key={m.id} className="animate-fs-enter flex items-start gap-3">
                        <WellsMark />
                        <div className="min-w-0 max-w-4xl flex-1">
                          <div className="mb-1.5 flex items-baseline gap-2">
                            <span className="text-sm font-semibold text-ink">{WELLS.name}</span>
                            <span className="text-[11px] uppercase tracking-[0.14em] text-mute">{WELLS.role}</span>
                          </div>
                          <div className="rounded-md border border-[var(--fs-border)] bg-paper/90 px-4 py-3.5">
                            <p className="text-[15px] leading-relaxed text-ink">{m.content}</p>
                            {m.answer ? (
                              <VisualRenderer
                                answer={m.answer}
                                onOpenEvidence={() => void openEvidence(m.answer)}
                              />
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ),
                  )}
                </>
              )}
              {loading ? (
                <div className="flex items-center gap-3 text-sm text-mute" aria-live="polite">
                  <WellsMark />
                  <span>
                    <span className="font-semibold text-ink">{WELLS.name}</span> is checking inspections and notes…
                  </span>
                </div>
              ) : null}
              {error ? (
                <div className="flex items-start gap-2 rounded-md bg-[#2a1216] px-3.5 py-3 text-sm text-[var(--fs-danger)] ring-1 ring-[#ff6b81]/30">
                  <IconX size={16} className="mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}
            </div>

            <form
              onSubmit={onSubmit}
              className="shrink-0 border-t border-[var(--fs-border)] bg-paper/95 p-4 backdrop-blur-md"
            >
              <div className="mx-auto flex max-w-3xl gap-2">
                <textarea
                  ref={inputRef}
                  className="h-14 flex-1 resize-none rounded-md border border-[var(--fs-border)] bg-paper px-3.5 py-3 text-sm text-ink outline-none transition placeholder:text-mute/70 focus:border-white/40"
                  placeholder={`Ask ${WELLS.name} about a well, a spill, or what’s holding up a repair…`}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(input);
                    }
                  }}
                  disabled={!userId || loading}
                />
                <button
                  type="submit"
                  disabled={!userId || loading || !input.trim()}
                  className="inline-flex items-center gap-1.5 self-end rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-black transition duration-150 hover:bg-neutral-200 active:opacity-80 disabled:opacity-40"
                >
                  <IconSend size={16} />
                  Ask
                </button>
              </div>
            </form>
          </section>

          <QuestionRail
            open={questionsOpen}
            onToggle={() => setQuestionsOpen((open) => !open)}
            disabled={loading}
            onAskTurn={(turn, q) => void askCatalogTurn(turn, q)}
          />

          {evidence ? (
            <aside className="flex min-h-0 w-[400px] shrink-0 flex-col border-l border-[var(--fs-border)] bg-paper">
              <div className="flex items-center justify-between border-b border-[var(--fs-border)] px-4 py-3">
                <h2 className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight">
                  <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-moss-soft text-moss">
                    <IconEvidence size={16} />
                  </span>
                  Sources
                  <span className="rounded-md bg-stone px-2 py-0.5 font-body text-xs font-medium text-mute">
                    {evidence.length}
                  </span>
                </h2>
                <button
                  type="button"
                  className="rounded-[10px] px-2.5 py-1 text-sm text-mute transition hover:bg-stone hover:text-ink"
                  onClick={() => setEvidence(null)}
                >
                  Close
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                {!evidence.length ? (
                  <div className="rounded-[14px] border border-dashed border-[var(--fs-border)] bg-stone/60 px-4 py-8 text-center text-sm text-mute">
                    No linked source records for this answer. The summary still stands — try a
                    question that cites inspections, notes, or procedure sections.
                  </div>
                ) : (
                  <ul className="space-y-2.5">
                    {evidence.map((item, i) => {
                      const kind = String(item.kind || "record");
                      const kindStyle =
                        kind === "sop" || kind === "manual"
                          ? "bg-moss-soft text-moss"
                          : kind === "inspection"
                            ? "bg-sky-50 text-sky-900"
                            : kind === "operator_note" || kind === "note"
                              ? "bg-copper-soft text-copper-deep"
                              : "bg-stone text-mute";
                      return (
                        <li
                          key={i}
                          className="rounded-md border border-[var(--fs-border)] bg-paper p-3 text-sm"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${kindStyle}`}
                            >
                              {kind.replace(/_/g, " ")}
                            </span>
                            <span className="font-medium text-ink">
                              {String(item.title || kind)}
                            </span>
                          </div>
                          {item.source_id ? (
                            <div className="mt-1 font-mono text-xs text-moss">
                              {String(item.source_id)}
                            </div>
                          ) : null}
                          {item.excerpt ? (
                            <p className="mt-2 whitespace-pre-wrap leading-relaxed text-mute">
                              {String(item.excerpt)}
                            </p>
                          ) : (
                            <p className="mt-2 text-xs italic text-mute/70">No excerpt on file</p>
                          )}
                          {item.source_path ? (
                            <div className="mt-2 truncate font-mono text-[11px] text-mute/70">
                              {String(item.source_path)}
                            </div>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </aside>
          ) : null}
        </div>
      </main>
    </div>
  );
}

type Area = { area_id: string; name: string };

const QUADS: Array<{ key: "NW" | "NE" | "SW" | "SE"; label: string }> = [
  { key: "NW", label: "Northwest" },
  { key: "NE", label: "Northeast" },
  { key: "SW", label: "Southwest" },
  { key: "SE", label: "Southeast" },
];

function quadrantOf(name: string): "NW" | "NE" | "SW" | "SE" | null {
  const n = name.toLowerCase();
  if (n.includes("northeast")) return "NE";
  if (n.includes("northwest")) return "NW";
  if (n.includes("southeast")) return "SE";
  if (n.includes("southwest")) return "SW";
  return null;
}

function blockLabel(name: string): string {
  const match = name.match(/block\s+\d+/i);
  if (!match) return name;
  return match[0].replace(/block/i, "Block");
}

function LeasePlat({ areas, onPick }: { areas: Area[]; onPick: (name: string) => void }) {
  const groups: Record<"NW" | "NE" | "SW" | "SE", Area[]> = { NW: [], NE: [], SW: [], SE: [] };
  const other: Area[] = [];
  for (const area of areas) {
    const quad = quadrantOf(area.name);
    if (quad) groups[quad].push(area);
    else other.push(area);
  }
  for (const key of Object.keys(groups) as Array<keyof typeof groups>) {
    groups[key].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  }

  return (
    <div className="px-3 pb-3">
      <div className="mb-2 flex items-baseline justify-between px-1">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/60">Lease</span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/45">North</span>
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/20 bg-white/20">
        {QUADS.map((quad) => (
          <div key={quad.key} className="min-h-[72px] bg-[#161310] px-2 py-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/55">{quad.label}</div>
            <div className="mt-1 space-y-0.5">
              {groups[quad.key].map((area) => (
                <button
                  key={area.area_id}
                  type="button"
                  title={`Ask about ${area.name}`}
                  onClick={() => onPick(area.name)}
                  className="block w-full rounded px-1 py-0.5 text-left text-xs font-medium text-white transition hover:bg-white/10"
                >
                  {blockLabel(area.name)}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {other.map((area) => (
        <button
          key={area.area_id}
          type="button"
          onClick={() => onPick(area.name)}
          className="mt-1 w-full rounded px-2 py-1 text-left text-xs text-white hover:bg-white/10"
        >
          {area.name}
        </button>
      ))}
    </div>
  );
}

function WellsHero({ signedIn }: { signedIn: boolean }) {
  return (
    <div className="flex max-w-md flex-col items-center text-center">
      <div className="rounded-full bg-white/6 p-3 ring-1 ring-white/20">
        <WellsMark size="hero" />
      </div>
      <h2 className="mt-5 text-[40px] font-semibold leading-none tracking-tight text-ink">{WELLS.name}</h2>
      <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-mute">{WELLS.role}</p>
      <p className="mt-4 max-w-sm text-sm leading-relaxed text-mute">{WELLS.line}</p>
      {signedIn ? null : (
        <p className="mt-3 text-xs text-mute">Choose who’s asking above, then ask {WELLS.name}.</p>
      )}
    </div>
  );
}

function QuestionRail({
  open,
  onToggle,
  disabled,
  onAskTurn,
}: {
  open: boolean;
  onToggle: () => void;
  disabled: boolean;
  onAskTurn: (turn: CatalogTurn, question: CatalogQuestion) => void;
}) {
  if (!open) {
    return (
      <aside className="flex w-12 shrink-0 flex-col border-l border-[var(--fs-border)] bg-paper">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={false}
          aria-label="Open questions"
          className="flex flex-1 items-center justify-center text-[11px] font-semibold uppercase tracking-[0.22em] text-ink hover:bg-white/5"
        >
          <span className="[writing-mode:vertical-rl]">Questions</span>
        </button>
      </aside>
    );
  }
  return (
    <aside className="flex min-h-0 w-[360px] shrink-0 flex-col border-l border-[var(--fs-border)] bg-paper">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded
        className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--fs-border)] px-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink"
      >
        Questions
        <span className="text-mute">Close</span>
      </button>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <QuestionCatalog disabled={disabled} onAskTurn={onAskTurn} />
      </div>
    </aside>
  );
}
