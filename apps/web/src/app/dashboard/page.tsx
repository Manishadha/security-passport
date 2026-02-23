"use client";

import { useEffect, useMemo, useState } from "react";
import { api, clearToken, getToken, type MeResponse, type TenantOverrides } from "@/lib/api";

async function downloadWithAuth(url: string, filename: string) {
  const token = getToken();
  if (!token) throw new Error("Missing token (please login again)");

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    try {
      const j = JSON.parse(txt);
      throw new Error(j?.detail ?? `Download failed: HTTP ${res.status}`);
    } catch {
      throw new Error(txt || `Download failed: HTTP ${res.status}`);
    }
  }

  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>("");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [overrides, setOverrides] = useState<TenantOverrides>({});

  const tokenPresent = Boolean(getToken());
  const templateCode = useMemo(() => "vendor_security_basics", []);
  const zipUrl = api.passportZipUrl(templateCode);
  const docxUrl = api.passportDocxUrl(templateCode);

  async function loadAll() {
    setErr("");
    setLoading(true);
    try {
      // these throw clean errors if token is missing/invalid
      const meRes = await api.me();
      setMe(meRes);

      const ov = await api.getOverrides();
      setOverrides(ov.overrides ?? {});
    } catch (e: any) {
      setMe(null);
      setOverrides({});
      setErr(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function savePatch(patch: TenantOverrides) {
    setErr("");
    try {
      const r = await api.patchOverrides(patch);
      setOverrides(r.overrides ?? {});
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  function logout() {
    clearToken();
    window.location.href = "/login";
  }

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <h1 style={{ fontSize: 28, marginBottom: 8 }}>Dashboard</h1>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "#666" }}>
            Token: <b>{tokenPresent ? "present" : "missing"}</b>
          </span>
          <button onClick={logout}>Logout</button>
        </div>
      </div>

      {loading && <p>Loading…</p>}

      {!loading && err && (
        <div style={{ padding: 12, background: "#fee", border: "1px solid #f99", marginBottom: 16 }}>
          <b>Error:</b> {err}
        </div>
      )}

      {!loading && (
        <>
          <section style={{ padding: 16, border: "1px solid #ddd", borderRadius: 8, marginBottom: 16 }}>
            <h2 style={{ marginTop: 0 }}>Session</h2>
            {me ? (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                <li>
                  <b>Email:</b> {me.email}
                </li>
                <li>
                  <b>Role:</b> {me.role}
                </li>
                <li>
                  <b>Tenant:</b> {me.tenant_id}
                </li>
                <li>
                  <b>User:</b> {me.user_id}
                </li>
              </ul>
            ) : (
              <p>No session loaded (login token missing/invalid)</p>
            )}

            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button onClick={loadAll}>Refresh</button>
              <button
                onClick={() => {
                  clearToken();
                  setErr("Token cleared. Please login again.");
                  setMe(null);
                  setOverrides({});
                }}
              >
                Clear token
              </button>
            </div>
          </section>

          <section style={{ padding: 16, border: "1px solid #ddd", borderRadius: 8, marginBottom: 16 }}>
            <h2 style={{ marginTop: 0 }}>Tenant Overrides</h2>

            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span>UI Theme</span>
                <select
                  value={overrides.ui_theme ?? "light"}
                  onChange={(e) => savePatch({ ui_theme: e.target.value as "dark" | "light" })}
                >
                  <option value="light">light</option>
                  <option value="dark">dark</option>
                </select>
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={Boolean(overrides.passport_zip_include_evidence)}
                  onChange={(e) => savePatch({ passport_zip_include_evidence: e.target.checked })}
                />
                <span>ZIP include evidence</span>
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={Boolean(overrides.passport_docx_include_evidence)}
                  onChange={(e) => savePatch({ passport_docx_include_evidence: e.target.checked })}
                />
                <span>DOCX include evidence</span>
              </label>
            </div>

            <pre style={{ marginTop: 12, background: "#f7f7f7", padding: 12, borderRadius: 8 }}>
              {JSON.stringify(overrides, null, 2)}
            </pre>
          </section>

          <section style={{ padding: 16, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>Passport Export</h2>
            <p style={{ marginTop: 0 }}>
              Template: <code>{templateCode}</code>
            </p>

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <button
                onClick={async () => {
                  try {
                    setErr("");
                    await downloadWithAuth(zipUrl, `${templateCode}.zip`);
                  } catch (e: any) {
                    setErr(e?.message ?? String(e));
                  }
                }}
              >
                Download ZIP
              </button>

              <button
                onClick={async () => {
                  try {
                    setErr("");
                    await downloadWithAuth(docxUrl, `${templateCode}.docx`);
                  } catch (e: any) {
                    setErr(e?.message ?? String(e));
                  }
                }}
              >
                Download DOCX
              </button>
            </div>

            <div style={{ marginTop: 10, fontSize: 12, color: "#666" }}>
              Downloads use <code>fetch</code> so the <code>Authorization</code> header is included.
              Opening the URL directly won’t include the token.
            </div>
          </section>
        </>
      )}
    </div>
  );
}