import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Answer, User, api } from "./api";
import { FieldSenseLogo } from "./FieldSenseLogo";
import { IconBot, IconEvidence, IconSend, IconSpark, IconUser, IconX } from "./icons";
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
  const [showCatalog, setShowCatalog] = useState(true);
  const [scriptCue, setScriptCue] = useState<ScriptCue | null>(null);
  const skipUserResetRef = useRef(false);

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
    setShowCatalog(true);
    setScriptCue(null);
  }, [userId]);

  function goHome() {
    setShowCatalog(true);
    setConversationId(null);
    setMessages([]);
    setEvidence(null);
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
    setShowCatalog(true);
    setScriptCue(null);
    const list = await api.conversations(userId);
    setConversations(list.conversations);
  }

  async function openChat(id: string) {
    if (!userId) return;
    setConversationId(id);
    setShowCatalog(false);
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
    setShowCatalog(false);
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

  const browsingCatalog = showCatalog || !messages.length;

  return (
    <div className="flex min-h-screen font-body text-ink">
      <aside className="fs-sidebar flex w-[272px] shrink-0 flex-col text-stone/95">
        <div className="border-b border-white/10 px-4 py-4">
          <button
            type="button"
            onClick={goHome}
            className="group w-full rounded-[12px] px-1 py-1 text-left transition hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-copper"
            aria-label="FieldSense home — open question catalog"
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
            className="w-full rounded-[10px] bg-copper px-3 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-copper-deep disabled:cursor-not-allowed disabled:opacity-40"
          >
            New conversation
          </button>
          <button
            type="button"
            onClick={() => setShowCatalog(true)}
            className="w-full rounded-[10px] border border-white/15 bg-white/5 px-3 py-2 text-sm font-medium text-stone/90 transition hover:bg-white/10"
          >
            Question catalog
          </button>
        </div>
        <div className="px-4 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-stone/45">
          Recent questions
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {conversations.length === 0 ? (
            <p className="px-2 py-3 text-xs leading-relaxed text-stone/45">
              Your questions will show up here.
            </p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => void openChat(c.id)}
                className={`mb-0.5 w-full rounded-[10px] px-3 py-2.5 text-left text-sm leading-snug transition ${
                  conversationId === c.id && !showCatalog
                    ? "bg-white/12 text-white"
                    : "text-stone/80 hover:bg-white/8 hover:text-white"
                }`}
              >
                {c.title}
              </button>
            ))
          )}
        </div>
        <div className="border-t border-white/10 px-4 py-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone/45">
            Field areas
          </div>
          <ul className="mt-2 space-y-1.5 text-sm text-stone/75">
            {areas.map((a) => (
              <li key={a.area_id} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-copper/80" />
                {a.name}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-[var(--fs-border)] bg-paper/90 px-5 py-3 backdrop-blur-md">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-mute">Who&apos;s asking</span>
            <select
              className="rounded-[10px] border border-[var(--fs-border)] bg-white px-2.5 py-1.5 text-ink shadow-soft"
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
              className="rounded-[10px] border border-[var(--fs-border)] bg-white px-2.5 py-1.5 font-mono text-xs text-ink shadow-soft"
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

        <div className="flex flex-1 overflow-hidden">
          <section className="flex min-w-0 flex-1 flex-col">
            <div className="flex-1 space-y-5 overflow-y-auto px-5 py-7">
              {browsingCatalog ? (
                <div>
                  <Empty
                    title="Question catalog"
                    body={
                      userId
                        ? "Copper = official FlytBase test-data questions for host submission. Moss = FieldSense showcase demos."
                        : "Pick a host question — we’ll sign in as the named asker automatically. Or choose who’s asking above first."
                    }
                  />
                  <div className="mt-6">
                    <QuestionCatalog
                      disabled={loading}
                      onAskTurn={(turn, q) => void askCatalogTurn(turn, q)}
                    />
                  </div>
                </div>
              ) : !userId ? (
                <Empty
                  title="Choose who you are"
                  body="Pick a person above, or open the question catalog and ask a host turn (it selects the asker for you)."
                />
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
                          className="rounded-[10px] bg-copper px-3 py-2 text-xs font-semibold text-white hover:bg-copper-deep disabled:opacity-40"
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
                        <div className="max-w-2xl rounded-[14px] rounded-br-md bg-copper-soft px-4 py-3 text-sm leading-relaxed text-ink">
                          {m.content}
                        </div>
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-copper text-white shadow-soft">
                          <IconUser size={16} />
                        </div>
                      </div>
                    ) : (
                      <div key={m.id} className="animate-fs-enter flex justify-start gap-2.5">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-pine text-copper-soft shadow-soft">
                          <IconBot size={16} />
                        </div>
                        <div className="min-w-0 max-w-4xl flex-1">
                          <div className="rounded-[14px] rounded-bl-md border border-[var(--fs-border)] bg-paper px-4 py-3.5 shadow-soft">
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
                <div className="flex items-center gap-2.5" aria-live="polite">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-pine text-copper-soft">
                    <IconBot size={16} />
                  </div>
                  <div className="inline-flex items-center gap-2 rounded-[14px] border border-[var(--fs-border)] bg-paper px-4 py-3 text-sm text-mute shadow-soft">
                    <span className="fs-dot-pulse" aria-hidden>
                      <i />
                      <i />
                      <i />
                    </span>
                    Checking inspections and notes…
                  </div>
                </div>
              ) : null}
              {error ? (
                <div className="flex items-start gap-2 rounded-[14px] bg-rose-50 px-3.5 py-3 text-sm text-[var(--fs-danger)] ring-1 ring-rose-100">
                  <IconX size={16} className="mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}
            </div>

            <form
              onSubmit={onSubmit}
              className="border-t border-[var(--fs-border)] bg-paper/95 p-4 backdrop-blur-md"
            >
              <div className="mx-auto flex max-w-3xl gap-2">
                <textarea
                  className="min-h-[56px] flex-1 resize-y rounded-[14px] border border-[var(--fs-border)] bg-white px-3.5 py-3 text-sm text-ink shadow-soft outline-none transition placeholder:text-mute/70 focus:border-copper/50 focus:ring-2 focus:ring-[var(--fs-focus)]"
                  placeholder="Ask about wells, safety, recalls, or what’s holding up repairs…"
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
                  className="inline-flex items-center gap-1.5 self-end rounded-[14px] bg-copper px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-copper-deep disabled:opacity-40"
                >
                  <IconSend size={16} />
                  Ask
                </button>
              </div>
            </form>
          </section>

          {evidence ? (
            <aside className="flex w-[400px] shrink-0 flex-col border-l border-[var(--fs-border)] bg-paper">
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
              <div className="flex-1 overflow-y-auto p-4">
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
                          className="rounded-[14px] border border-[var(--fs-border)] bg-white p-3 text-sm shadow-soft"
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

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="mx-auto max-w-xl px-2 text-center">
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-pine text-copper-soft shadow-lift">
        <IconSpark size={24} />
      </div>
      <h2 className="font-display text-[1.75rem] font-semibold tracking-tight text-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-mute">{body}</p>
    </div>
  );
}
