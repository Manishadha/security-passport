"use client";

import React, { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:58000";

type Props = {
  params: Promise<{ token: string }> | { token: string };
};

type PublicItem = {
  evidence_id: string;
  title?: string | null;
  category?: string | null;
  tags?: string[] | null;
  original_filename?: string | null;
  uploaded_at?: string | null;
  size_bytes?: number | null;
};

type PublicShare = {
  name?: string;
  policy_version?: string;
  expires_at?: string | null;
  items?: PublicItem[];
};

function isPromise<T>(v: any): v is Promise<T> {
  return v && typeof v.then === "function";
}

function fmt(ts?: string | null) {
  if (!ts) return "-";
  try {
    return new Date(ts).toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return ts;
  }
}

function fmtBytes(n?: number | null) {
  if (n == null) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v = v / 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

async function fetchJsonOrText(url: string) {
  const res = await fetch(url);
  const text = await res.text();
  let data: any;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  return { res, data, text };
}

export default function PublicSharePage({ params }: Props) {
  const resolved = isPromise<{ token: string }>(params)
    ? React.use(params)
    : params;

  const token = resolved.token;

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [data, setData] = useState<PublicShare | null>(null);

  async function load() {
    setErr("");
    setLoading(true);
    try {
      const { res, data } = await fetchJsonOrText(`${API_BASE}/share/${token}`);
      if (!res.ok) {
        throw new Error(data?.detail ?? `HTTP ${res.status}`);
      }
      setData(data as PublicShare);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function downloadEvidence(evidenceId: string) {
    setErr("");
    try {
      const url = `${API_BASE}/share/${token}/evidence/${evidenceId}/download`;

      // This endpoint returns JSON: { url: "presigned...", expires_in_seconds: 300 }
      const { res, data, text } = await fetchJsonOrText(url);

      // If backend ever returns a redirect/file directly, handle it:
      if (res.redirected) {
        window.location.href = res.url;
        return;
      }

      if (!res.ok) {
        throw new Error(data?.detail ?? text ?? `HTTP ${res.status}`);
      }

      // If JSON with presigned URL:
      const presigned = data?.url;
      if (typeof presigned === "string" && presigned.startsWith("http")) {
        window.location.href = presigned; // triggers actual download
        return;
      }

      // Unexpected shape fallback:
      throw new Error("Unexpected download response (missing url)");
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  const items = data?.items ?? [];

  return (
    <div
      style={{
        padding: 24,
        maxWidth: 980,
        margin: "0 auto",
        color: "#111",
        fontFamily:
          'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji"',
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 28, margin: 0 }}>Shared Evidence</h1>
          <div style={{ color: "#444", marginTop: 6 }}>
            {data?.name ? <span><b>{data.name}</b></span> : <span>Public share link</span>}
            {data?.policy_version ? <span> · policy {data.policy_version}</span> : null}
          </div>
        </div>

        <button
          onClick={load}
          style={{
            padding: "8px 12px",
            borderRadius: 10,
            border: "1px solid #ddd",
            background: "#fff",
            cursor: "pointer",
            height: 40,
          }}
        >
          Refresh
        </button>
      </div>

      <div
        style={{
          marginTop: 16,
          background: "#fafafa",
          border: "1px solid #e5e5e5",
          borderRadius: 12,
          padding: 14,
        }}
      >
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", color: "#222" }}>
          <div>
            <div style={{ fontSize: 12, color: "#666" }}>Expires</div>
            <div style={{ fontWeight: 600 }}>{fmt((data as any)?.expires_at ?? null)}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#666" }}>Items</div>
            <div style={{ fontWeight: 600 }}>{items.length}</div>
          </div>
        </div>
      </div>

      {loading && <p style={{ marginTop: 16 }}>Loading…</p>}

      {!loading && err && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: "#fff5f5",
            border: "1px solid #ffb3b3",
            borderRadius: 12,
          }}
        >
          <b>Error:</b> {err}
        </div>
      )}

      {!loading && !err && (
        <div
          style={{
            marginTop: 16,
            border: "1px solid #e5e5e5",
            borderRadius: 12,
            overflow: "hidden",
            background: "#fff",
          }}
        >
          {items.length === 0 ? (
            <div style={{ padding: 16, color: "#333" }}>No evidence attached to this share link.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "#f3f4f6" }}>
                  <th style={{ textAlign: "left", padding: 12, fontSize: 13, color: "#333" }}>Title</th>
                  <th style={{ textAlign: "left", padding: 12, fontSize: 13, color: "#333" }}>Category</th>
                  <th style={{ textAlign: "left", padding: 12, fontSize: 13, color: "#333" }}>Tags</th>
                  <th style={{ textAlign: "left", padding: 12, fontSize: 13, color: "#333" }}>Uploaded</th>
                  <th style={{ textAlign: "left", padding: 12, fontSize: 13, color: "#333" }}>Size</th>
                  <th style={{ textAlign: "left", padding: 12, fontSize: 13, color: "#333" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const tags = (it.tags ?? []).filter(Boolean).join(", ");
                  return (
                    <tr key={it.evidence_id} style={{ borderTop: "1px solid #eee" }}>
                      <td style={{ padding: 12, verticalAlign: "top" }}>
                        <div style={{ fontWeight: 600 }}>{it.title ?? it.original_filename ?? it.evidence_id}</div>
                        <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                          id: <code style={{ fontSize: 11 }}>{it.evidence_id}</code>
                        </div>
                      </td>
                      <td style={{ padding: 12, verticalAlign: "top", color: "#333" }}>
                        {it.category ?? "-"}
                      </td>
                      <td style={{ padding: 12, verticalAlign: "top", color: "#333" }}>
                        {tags || "-"}
                      </td>
                      <td style={{ padding: 12, verticalAlign: "top", color: "#333" }}>
                        {fmt(it.uploaded_at ?? null)}
                      </td>
                      <td style={{ padding: 12, verticalAlign: "top", color: "#333" }}>
                        {fmtBytes(it.size_bytes ?? null)}
                      </td>
                      <td style={{ padding: 12, verticalAlign: "top" }}>
                        <button
                          onClick={() => downloadEvidence(it.evidence_id)}
                          style={{
                            padding: "8px 10px",
                            borderRadius: 10,
                            border: "1px solid #ddd",
                            background: "#fff",
                            cursor: "pointer",
                          }}
                        >
                          Download
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div style={{ marginTop: 12, fontSize: 12, color: "#666" }}>
        Downloads use a short-lived link (expires in ~5 minutes).
      </div>
    </div>
  );
}