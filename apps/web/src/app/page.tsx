"use client";

import { useEffect, useMemo, useState } from "react";
import { api, clearToken, type EvidenceItem, type TenantOverrides } from "@/lib/api";
import { useRouter } from "next/navigation";

async function downloadWithAuth(url: string, filename: string) {
  const token = localStorage.getItem("sp_token");
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
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string>("");

  const [me, setMe] = useState<Awaited<ReturnType<typeof api.me>> | null>(null);
  const [overrides, setOverrides] = useState<TenantOverrides>({});

  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [file, setFile] = useState<File | null>(null);

  const templateCode = useMemo(() => "vendor_security_basics", []);

  async function loadAll() {
    setErr("");
    setLoading(true);
    try {
      const meRes = await api.me();
      setMe(meRes);

      const ov = await api.getOverrides();
      setOverrides(ov.overrides ?? {});

      const ev = await api.listEvidence();
      setEvidence(ev ?? []);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setMe(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // if token missing, go login
    if (!localStorage.getItem("sp_token")) {
      router.push("/login");
      return;
    }
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

  async function doUpload() {
    setErr("");
    if (!file) {
      setErr("Pick a file first");
      return;
    }
    try {
      // create evidence record first
      const created = await api.createEvidence({
        original_filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        metadata: {},
      });

      // upload bytes
      await api.uploadEvidenceFile(created.id, file);

      // refresh list
      const ev = await api.listEvidence();
      setEvidence(ev ?? []);
      setFile(null);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function downloadEvidence(ev: EvidenceItem) {
    setErr("");
    try {
      const dl = await api.getEvidenceDownloadUrl(ev.id);
      await downloadWithAuth(dl.url, ev.original_filename || `${ev.id}.bin`);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  const zipUrl = api.passportZipUrl(templateCode);
  const docxUrl = api.passportDocxUrl(templateCode);

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <h1 style={{ fontSize: 28, marginBottom: 10 }}>Dashboard</h1>

      {loading && <p>Loading…</p>}

      {!loading && err && (
        <div style={{ padding: 12, background: "#fee", border: "1px solid #f99", marginBottom: 16 }}>
          <b>Error:</b> {err}
        </div>
      )}

      {!loading && (
        <>
          <section style={{ padding: 16, border: "1px solid #ddd", borderRadius: 8, marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <h2 style={{ marginTop: 0 }}>Session</h2>
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => router.push("/evidence")}>Evidence Library</button>

                <button onClick={loadAll}>Refresh</button>

                <button
                  onClick={() => {
                    clearToken();
                    router.push("/login");
                  }}
                >
                  Logout
                </button>
              </div>
            </div>

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
              <p>No session loaded (login again)</p>
            )}
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

          <section style={{ padding: 16, border: "1px solid #ddd", borderRadius: 8, marginBottom: 16 }}>
            <h2 style={{ marginTop: 0 }}>Evidence</h2>

            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <button onClick={doUpload}>Upload</button>
            </div>

            <div style={{ marginTop: 12 }}>
              {evidence.length === 0 ? (
                <p>No evidence yet.</p>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>File</th>
                      <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Created</th>
                      <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.map((ev) => (
                      <tr key={ev.id}>
                        <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                          {(ev as any).original_filename || ev.id}
                        </td>
                        <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                          {(ev as any).created_at || "-"}
                        </td>
                        <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                          <button onClick={() => downloadEvidence(ev)}>Download</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
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
              (Downloads are done via fetch so the Authorization header is included.)
            </div>
          </section>
        </>
      )}
    </div>
  );
}