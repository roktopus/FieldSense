const API_BASE = import.meta.env.VITE_API_BASE || "";

export type User = {
  user_id: string;
  name: string;
  role: string;
  team_id?: string;
};

export type Answer = {
  schema_version?: string;
  run_id?: string;
  result_set_id?: string;
  status?: string;
  kind?: string;
  summary?: string;
  visuals?: Array<Record<string, unknown>>;
  rows?: unknown[] | null;
  data?: Record<string, unknown>;
  conflicts?: unknown[];
  coverage?: Record<string, unknown>;
  citations?: Array<{ id?: string; label?: string }>;
  warnings?: string[];
  scope?: Record<string, unknown>;
};

async function req<T>(path: string, init: RequestInit = {}, userId?: string): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set("Content-Type", "application/json");
  if (userId) headers.set("X-User-Id", userId);
  const asOf = localStorage.getItem("fieldsense_as_of");
  if (asOf) headers.set("X-Analysis-Clock", asOf);
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export const api = {
  users: () => req<{ users: User[] }>("/api/v1/users"),
  selectUser: (user_id: string) =>
    req<{ user_id: string; name: string; session_id: string }>("/api/v1/session/user", {
      method: "POST",
      body: JSON.stringify({ user_id }),
    }),
  conversations: (userId: string) =>
    req<{ conversations: Array<{ id: string; title: string; updated_at?: string }> }>(
      "/api/v1/conversations",
      {},
      userId,
    ),
  createConversation: (userId: string, title = "New chat") =>
    req<{ id: string; title: string }>(
      "/api/v1/conversations",
      { method: "POST", body: JSON.stringify({ title }) },
      userId,
    ),
  getConversation: (userId: string, id: string) =>
    req<{
      id: string;
      title: string;
      messages: Array<{ id: string; role: string; content: string; answer?: Answer }>;
    }>(`/api/v1/conversations/${id}`, {}, userId),
  run: (userId: string, conversationId: string, message: string) =>
    req<{ run_id: string; status: string; answer: Answer }>(
      `/api/v1/conversations/${conversationId}/runs`,
      { method: "POST", body: JSON.stringify({ message }) },
      userId,
    ),
  evidence: (userId: string, resultSetId: string) =>
    req<{ items: Array<Record<string, unknown>>; total: number }>(
      `/api/v1/evidence?result_set_id=${resultSetId}`,
      {},
      userId,
    ),
  areas: () => req<{ areas: Array<{ area_id: string; name: string }> }>("/api/v1/areas"),
  importLatest: () =>
    req<{
      status: string;
      dataset_version?: string | null;
      evaluation_as_of?: string;
      dataset_profile?: string;
    }>("/api/v1/import/latest"),
  wells: (q = "") =>
    req<{ wells: Array<{ asset_id: string; name: string; well_type: string }> }>(
      `/api/v1/wells?q=${encodeURIComponent(q)}`,
    ),
};
