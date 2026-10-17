import { FormEvent, useEffect, useMemo, useState } from "react";
import { Answer, User, api } from "./api";
import { IconBot, IconEvidence, IconSend, IconSpark, IconUser, IconX } from "./icons";
import { VisualRenderer } from "./Visuals";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer?: Answer;
};

const SUGGESTIONS = [
  "Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.",
  "Which wells in Northeast Block 7 had the most downtime between 16 June and 16 October 2026, and why? Show a bar chart.",
  "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.",
  "Show a heatmap of 2026 spills by geographic area and month.",
];

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
  const [importInfo, setImportInfo] = useState<string>("Import not run yet");
  const [asOf, setAsOf] = useState(() => localStorage.getItem("fieldsense_as_of") || "2026-10-17T00:00:00Z");

  const activeUser = useMemo(() => users.find((u) => u.user_id === userId), [users, userId]);

  useEffect(() => {
    api.users().then((r) => setUsers(r.users)).catch((e) => setError(String(e)));
    api.areas().then((r) => setAreas(r.areas)).catch(() => undefined);
    api.importLatest().then((r) => {
      if (r.status === "none") setImportInfo("No import yet — run make import-data");
      else setImportInfo(`Import ${r.status}: ${r.dataset_version || ""}`);
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
    setConversationId(null);
    setMessages([]);
    setEvidence(null);
  }, [userId]);

  async function newChat() {
    if (!userId) return;
    const c = await api.createConversation(userId);
    setConversationId(c.id);
    setMessages([]);
    setEvidence(null);
    const list = await api.conversations(userId);
    setConversations(list.conversations);
  }

  async function openChat(id: string) {
    if (!userId) return;
    setConversationId(id);
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

  async function send(text: string) {
    if (!userId || !text.trim()) return;
    setError(null);
    setLoading(true);
    try {
      let cid = conversationId;
      if (!cid) {
        const c = await api.createConversation(userId, text.slice(0, 60));
        cid = c.id;
        setConversationId(cid);
      }
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: text }]);
      setInput("");
      const res = await api.run(userId, cid, text);
      setMessages((prev) => [
        ...prev,
        {
          id: res.run_id,
          role: "assistant",
          content: res.answer?.summary || "Done.",
          answer: res.answer,
        },
      ]);
      const list = await api.conversations(userId);
      setConversations(list.conversations);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  async function openEvidence(answer?: Answer) {
    if (!userId || !answer?.result_set_id) return;
    const r = await api.evidence(userId, answer.result_set_id);
    setEvidence(r.items);
  }

  return (
    <div className="flex min-h-screen bg-[var(--fs-bg)] text-ink">
      <aside className="flex w-[260px] shrink-0 flex-col bg-sidebar text-slate-100">
        <div className="border-b border-white/10 px-4 py-4">
          <div className="font-display text-xl tracking-tight">FieldSense</div>
          <div className="text-xs text-slate-300">Asset Intelligence Copilot</div>
        </div>
        <div className="p-3">
          <button
            type="button"
            onClick={() => void newChat()}
            disabled={!userId}
            className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-teal-600 disabled:opacity-40"
          >
            + New chat
          </button>
        </div>
        <div className="px-3 text-xs uppercase tracking-wide text-slate-400">Conversations</div>
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {conversations.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => void openChat(c.id)}
              className={`mb-1 w-full rounded-md px-2 py-2 text-left text-sm hover:bg-white/10 ${
                conversationId === c.id ? "bg-white/15" : ""
              }`}
            >
              {c.title}
            </button>
          ))}
        </div>
        <div className="border-t border-white/10 px-3 py-3">
          <div className="text-xs uppercase tracking-wide text-slate-400">Areas</div>
          <ul className="mt-1 space-y-1 text-sm text-slate-300">
            {areas.map((a) => (
              <li key={a.area_id}>{a.name}</li>
            ))}
          </ul>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-3">
          <label className="text-sm">
            <span className="mr-2 text-slate-500">Demo user</span>
            <select
              className="rounded-md border border-slate-300 px-2 py-1"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
            >
              <option value="">Select…</option>
              {users.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.name} ({u.role})
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mr-2 text-slate-500">As of</span>
            <input
              className="rounded-md border border-slate-300 px-2 py-1 font-mono text-xs"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
          <div className="text-xs text-slate-500">{importInfo}</div>
          <div className="ml-auto text-xs text-amber-700">
            Demo identity — not production authentication
          </div>
        </header>

        <div className="flex flex-1 overflow-hidden">
          <section className="flex min-w-0 flex-1 flex-col">
            <div className="flex-1 space-y-5 overflow-y-auto px-4 py-6">
              {!userId ? (
                <Empty title="Select a demo user to begin" body="Private chats are scoped to the selected identity." />
              ) : !messages.length ? (
                <div>
                  <Empty
                    title="Ask about your wells"
                    body="Answers are grounded in inspections, manuals, reports, and corrections."
                  />
                  <div className="mx-auto mt-5 grid max-w-3xl gap-2.5">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => void send(s)}
                        className="group flex gap-3 rounded-xl border border-slate-200/90 bg-white px-4 py-3.5 text-left text-sm shadow-[0_1px_0_rgba(15,23,42,0.03)] transition hover:border-accent/40 hover:bg-teal-50/30"
                      >
                        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-accent group-hover:bg-accent group-hover:text-white">
                          <IconSpark size={15} />
                        </span>
                        <span className="leading-relaxed text-slate-700">{s}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m) =>
                  m.role === "user" ? (
                    <div key={m.id} className="flex justify-end gap-2.5">
                      <div className="max-w-2xl rounded-2xl rounded-br-md bg-[#dbeafe] px-4 py-3 text-sm leading-relaxed text-slate-900">
                        {m.content}
                      </div>
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sky-700 text-white">
                        <IconUser size={16} />
                      </div>
                    </div>
                  ) : (
                    <div key={m.id} className="flex justify-start gap-2.5">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sidebar text-teal-200">
                        <IconBot size={16} />
                      </div>
                      <div className="min-w-0 max-w-4xl flex-1">
                        <div className="rounded-2xl rounded-bl-md border border-slate-200/90 bg-white px-4 py-3 shadow-[0_1px_0_rgba(15,23,42,0.04)]">
                          <p className="text-sm leading-relaxed text-slate-800">{m.content}</p>
                          {m.answer ? (
                            <VisualRenderer answer={m.answer} onOpenEvidence={() => void openEvidence(m.answer)} />
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ),
                )
              )}
              {loading ? (
                <div className="flex items-center gap-2.5" aria-live="polite">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-sidebar text-teal-200">
                    <IconBot size={16} />
                  </div>
                  <div className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
                    <span className="fs-dot-pulse" aria-hidden>
                      <i />
                      <i />
                      <i />
                    </span>
                    Calculating from inspections…
                  </div>
                </div>
              ) : null}
              {error ? (
                <div className="flex items-start gap-2 rounded-xl bg-rose-50 px-3 py-3 text-sm text-rose-800 ring-1 ring-rose-100">
                  <IconX size={16} className="mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}
            </div>

            <form onSubmit={onSubmit} className="border-t border-slate-200 bg-white/90 p-4 backdrop-blur">
              <div className="mx-auto flex max-w-3xl gap-2">
                <textarea
                  className="min-h-[52px] flex-1 resize-y rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none ring-accent/0 transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                  placeholder="Ask about your wells, spills, downtime, or compliance…"
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
                  className="inline-flex items-center gap-1.5 self-end rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:opacity-40"
                >
                  <IconSend size={16} />
                  Send
                </button>
              </div>
            </form>
          </section>

          {evidence ? (
            <aside className="w-[380px] shrink-0 overflow-y-auto border-l border-slate-200 bg-white p-4">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="flex items-center gap-2 font-display text-lg">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-50 text-accent">
                    <IconEvidence size={16} />
                  </span>
                  Evidence
                </h2>
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
                  onClick={() => setEvidence(null)}
                >
                  Close
                </button>
              </div>
              <ul className="space-y-2.5">
                {evidence.map((item, i) => (
                  <li
                    key={i}
                    className="rounded-xl border border-slate-200/90 bg-gradient-to-b from-white to-slate-50/80 p-3 text-sm"
                  >
                    <div className="font-medium text-ink">{String(item.title || item.kind)}</div>
                    <div className="mt-0.5 font-mono text-xs text-sky-700">{String(item.source_id || "")}</div>
                    {item.excerpt ? (
                      <p className="mt-2 leading-relaxed text-slate-600">{String(item.excerpt)}</p>
                    ) : null}
                    {item.source_path ? (
                      <div className="mt-2 truncate font-mono text-[11px] text-slate-400">
                        {String(item.source_path)}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </aside>
          ) : null}
        </div>
      </main>
    </div>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-dashed border-slate-300/90 bg-white/80 p-8 text-center">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-50 text-accent">
        <IconSpark size={22} />
      </div>
      <h2 className="font-display text-2xl tracking-tight">{title}</h2>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{body}</p>
    </div>
  );
}
