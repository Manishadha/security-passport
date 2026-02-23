const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:58000";

export type TenantOverrides = {
  ui_theme?: "dark" | "light";
  passport_zip_include_evidence?: boolean;
  passport_docx_include_evidence?: boolean;
  evidence_retention_days?: number;
};

export type OverridesResponse = {
  tenant_id: string;
  overrides: TenantOverrides;
};

export type MeResponse = {
  user_id: string;
  tenant_id: string;
  role: string;
  email: string;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("sp_token");
}

export function setToken(token: string) {
  localStorage.setItem("sp_token", token);
}

export function clearToken() {
  localStorage.removeItem("sp_token");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();

  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };

  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  const text = await res.text();

  let data: any;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    throw new Error(data?.detail ?? `HTTP ${res.status}`);
  }

  return data as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<MeResponse>("/me"),

  getOverrides: () => request<OverridesResponse>("/tenants/me/overrides"),

  patchOverrides: (overrides: TenantOverrides) =>
    request<{ ok: boolean; tenant_id: string; overrides: TenantOverrides }>(
      "/tenants/me/overrides",
      {
        method: "PATCH",
        body: JSON.stringify({ overrides }),
      }
    ),

  passportZipUrl: (code: string) => `${API_BASE}/passport/${code}.zip`,
  passportDocxUrl: (code: string) => `${API_BASE}/passport/${code}.docx`,
};