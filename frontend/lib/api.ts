/** Browser → REST gateway only (no gRPC in the client). */

export function getApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";
  return raw.replace(/\/$/, "");
}

export type ApiError = { ok: false; status: number; detail: string };
export type ApiOk<T> = { ok: true; data: T };
export type ApiResult<T> = ApiOk<T> | ApiError;

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  const base = getApiBase();
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    let detail = text || res.statusText;
    if (typeof body === "object" && body !== null && "detail" in body) {
      const d = (body as { detail: unknown }).detail;
      detail = typeof d === "string" ? d : JSON.stringify(d);
    }
    return { ok: false, status: res.status, detail };
  }
  return { ok: true, data: body as T };
}
