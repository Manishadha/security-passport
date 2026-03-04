const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:58000";

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
  const isBrowser = typeof window !== "undefined";
  const token = isBrowser ? localStorage.getItem("sp_token") : null;

  const headers: Record<string, string> = {
    ...(init.headers as any),
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
    // Helpful: include path + status to debug auth quickly
    const msg = data?.detail ?? `HTTP ${res.status} (${path})`;
    throw new Error(msg);
  }

  return data as T;
}

export type MeResponse = {
  user_id: string;
  tenant_id: string;
  role: string;
  email: string;
};

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
export type EvidenceItem = {
  id: string;
  title: string;
  description?: string | null;
  category?: string | null;
  tags?: string[];

  created_at?: string;
  updated_at?: string;
  deleted_at?: string | null;

  storage_key?: string | null;
  original_filename?: string | null;
  uploaded_at?: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  content_hash?: string | null;

  
  expires_at?: string | null;
  effective_expires_at?: string | null;
  freshness_status?: "fresh" | "expiring" | "expired" | "no_expiry";
  age_days?: number | null;
  last_verified_at?: string | null;
  evidence_period_start?: string | null;
  evidence_period_end?: string | null;
  source_system?: string | null;
  source_ref?: string | null;
};

export type EvidenceCreateResponse = EvidenceItem & {
  upload_url?: string; // if  API returns it
};

export type EvidenceDownloadResponse = {
  url: string;
  expires_in_seconds: number;
};

export const api = {
  // =========================
  // AUTH
  // =========================

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<MeResponse>("/me"),

  // =========================
  // TENANT OVERRIDES
  // =========================

  getOverrides: () =>
    request<OverridesResponse>("/tenants/me/overrides"),

  patchOverrides: (overrides: TenantOverrides) =>
    request<OverridesResponse & { ok?: boolean }>(
      "/tenants/me/overrides",
      {
        method: "PATCH",
        body: JSON.stringify({ overrides }),
      }
    ),

  // =========================
  // PASSPORT EXPORT
  // =========================

  passportZipUrl: (code: string) =>
    `${API_BASE}/passport/${code}.zip`,

  passportDocxUrl: (code: string) =>
    `${API_BASE}/passport/${code}.docx`,

  // =========================
  // EVIDENCE (BASIC)
  // =========================

  listEvidence: () =>
    request<EvidenceItem[]>("/evidence"),

  createEvidence: (payload: Record<string, any>) =>
    request<EvidenceCreateResponse>("/evidence", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // =========================
  // EVIDENCE (EXTENDED)
  // =========================

  listEvidencePaged: (params?: {
    limit?: number
    offset?: number
    include_deleted?: boolean
  }) => {
    const limit = params?.limit ?? 50
    const offset = params?.offset ?? 0
    const include = params?.include_deleted ? "true" : "false"

    return request<EvidenceItem[]>(
      `/evidence?limit=${limit}&offset=${offset}&include_deleted=${include}`
    )
  },

  getEvidence: (id: string) =>
    request<EvidenceItem>(`/evidence/${id}`),

  patchEvidence: (
    id: string,
    patch: {
      title?: string
      description?: string | null
      category?: string | null
      tags?: string[]

      
      expires_at?: string | null
      last_verified_at?: string | null
      evidence_period_start?: string | null
      evidence_period_end?: string | null
      source_system?: string | null
      source_ref?: string | null
    }
  ) =>
    request<{ ok: boolean; changed: boolean }>(`/evidence/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  deleteEvidence: (id: string) =>
    request<{ ok: boolean }>(`/evidence/${id}`, {
      method: "DELETE",
    }),

  // =========================
  // EVIDENCE FILE UPLOAD
  // =========================

  uploadEvidenceFile: async (
    evidenceId: string,
    file: File
  ) => {
    const token = getToken()

    if (!token)
      throw new Error("Missing token (login first)")

    const form = new FormData()
    form.append("file", file)

    const res = await fetch(
      `${API_BASE}/evidence/${evidenceId}/upload`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: form,
      }
    )

    const text = await res.text()

    let data: any

    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = text
    }

    if (!res.ok)
      throw new Error(data?.detail ?? `HTTP ${res.status}`)

    return data
  },

  getEvidenceDownloadUrl: (evidenceId: string) =>
    request<EvidenceDownloadResponse>(
      `/evidence/${evidenceId}/download`
    ),

  // share links (authenticated management)
  listShareLinks: () => request<ShareLink[]>("/share-links"),

  createShareLink: (payload: ShareLinkCreateRequest) =>
    request<ShareLinkCreateResponse>("/share-links", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteShareLink: (shareLinkId: string) =>
    request<{ ok: boolean }>(`/share-links/${shareLinkId}`, {
      method: "DELETE",
    }),

  addShareLinkItem: (shareLinkId: string, evidenceId: string) =>
    request<{ ok: boolean }>(`/share-links/${shareLinkId}/items`, {
      method: "POST",
      body: JSON.stringify({ evidence_id: evidenceId }),
    }),

  // =========================
  // SHARE LINKS (PUBLIC)
  // =========================

  getPublicShare: async (token: string) => {
    const res = await fetch(
      `${API_BASE}/share/${token}`
    )

    const text = await res.text()

    let data: any

    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = text
    }

    if (!res.ok)
      throw new Error(
        data?.detail ?? `HTTP ${res.status}`
      )

    return data
  },

  publicEvidenceDownloadUrl: (
    token: string,
    evidenceId: string
  ) =>
    `${API_BASE}/share/${token}/evidence/${evidenceId}/download`,
}

export type ShareLink = {
  id: string;
  name: string;
  created_at?: string;
  expires_at?: string | null;
  revoked_at?: string | null;
  policy_version?: string;
  settings?: any;
  // Some APIs return token only on create
  token?: string;
  url?: string;
};

export type ShareLinkCreateRequest = {
  name: string;
  expires_at?: string | null; // ISO string
  settings?: any;
  policy_version?: string;
};

export type ShareLinkCreateResponse = ShareLink & {
  token?: string; // show once
  public_url?: string;
};

export type ShareLinkItem = {
  id: string;
  share_link_id: string;
  evidence_id: string;
  created_at?: string;
};

export type ShareLinkAccessLog = {
  id: string;
  share_link_id: string;
  action: string;
  evidence_id?: string | null;
  ip?: string | null;
  user_agent?: string | null;
  created_at?: string;
};

