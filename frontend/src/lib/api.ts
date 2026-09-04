const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export interface DocumentSummary {
  id: string;
  file_name: string;
  file_type: string;
  document_type: string;
  status: "UPLOADED" | "PROCESSING" | "COMPLETED" | "FAILED";
  confidence: number | null;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProcessingAttempt {
  attempt_number: number;
  status: string;
  stage: string | null;
  error_type: string | null;
  error_message: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  attempts: ProcessingAttempt[];
}

export interface DocumentResult {
  document_id: string;
  status: string;
  document_type: string;
  confidence: number;
  extracted_data: Record<string, unknown>;
  masked_data: Record<string, unknown>;
  error_message: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const resp = await fetch(`${BASE}${path}`, { ...init, headers });
  if (resp.status === 204) return undefined as T;
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    throw new ApiError(resp.status, detail || resp.statusText);
  }
  return body as T;
}

export const api = {
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/api/v1/auth/register", null, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/v1/auth/login", null, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  listDocuments: (token: string, limit = 50) =>
    request<Page<DocumentSummary>>(`/api/v1/documents?limit=${limit}`, token),

  getDocument: (token: string, id: string) =>
    request<DocumentDetail>(`/api/v1/documents/${id}`, token),

  getResult: (token: string, id: string) =>
    request<DocumentResult>(`/api/v1/documents/${id}/result`, token),

  uploadDocument: (token: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ id: string; status: string }>("/api/v1/documents", token, {
      method: "POST",
      body: fd,
    });
  },

  retryDocument: (token: string, id: string) =>
    request<DocumentSummary>(`/api/v1/documents/${id}/retry`, token, { method: "POST" }),

  deleteDocument: (token: string, id: string) =>
    request<void>(`/api/v1/documents/${id}`, token, { method: "DELETE" }),
};

export { ApiError };
