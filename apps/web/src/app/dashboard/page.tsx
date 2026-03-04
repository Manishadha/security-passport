"use client";

import { useEffect, useMemo, useState } from "react";
import { api, clearToken, type TenantOverrides, type EvidenceItem } from "@/lib/api";
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

  const [evidenceCount, setEvidenceCount] = useState(0);
  const [uploadedCount, setUploadedCount] = useState(0);

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const templateCode = useMemo(() => "vendor_security_basics", []);

  async function loadAll() {
    setErr("");
    setLoading(true);
    try {
      const meRes = await api.me();
      setMe(meRes);

      const ov = await api.getOverrides();
      setOverrides(ov.overrides ?? {});

      // lightweight evidence summary
      const ev: EvidenceItem[] = await api.listEvidencePaged({ limit: 200, offset: 0, include_deleted: false });
      const total = ev?.length ?? 0;
      const uploaded = (ev ?? []).filter((x) => Boolean(x.uploaded_at) && Boolean(x.storage_key) && !x.deleted_at).length;

      setEvidenceCount(total);
      setUploadedCount(uploaded);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setMe(null);
      setEvidenceCount(0);
      setUploadedCount(0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
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

  async function quickUpload() {
    setErr("");
    if (!file) {
      setErr("Pick a file first");
      return;
    }
    setUploading(true);
    try {
      const created = await api.createEvidence({
        title: file.name,
        original_filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        tags: [],
        category: null,
      });

      // upload (will be protected by B) if already uploaded
      await api.uploadEvidenceFile(created.id, file);

      setFile(null);
      await loadAll();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setUploading(false);
    }
  }

  const zipUrl = api.passportZipUrl(templateCode);
  const docxUrl = api.passportDocxUrl(templateCode);

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <h1 style={{ fontSize: 28, marginBottom: 10 }}>Dashboard</h1>
      <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <button onClick={() => router.push("/evidence")}>Evidence Library</button>
        <button onClick={() => router.push("/share-links")}>Share Links</button>
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
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <h2 style={{ marginTop: 0 }}>Session</h2>
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => router.push("/evidence")}>Evidence Library</button>
                <button onClick={() => router.push("/share-links")}>Share Links</button>
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
                <li><b>Email:</b> {me.email}</li>
                <li><b>Role:</b> {me.role}</li>
                <li><b>Tenant:</b> {me.tenant_id}</li>
                <li><b>User:</b> {me.user_id}</li>
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
            <h2 style={{ marginTop: 0 }}>Evidence Summary</h2>

            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center" }}>
              <div><b>Total:</b> {evidenceCount}</div>
              <div><b>Uploaded:</b> {uploadedCount}</div>
              <div><b>Pending:</b> {Math.max(0, evidenceCount - uploadedCount)}</div>

              <button onClick={() => router.push("/evidence")}>Open Evidence Library</button>
            </div>

            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #eee" }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Quick upload</div>
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <button onClick={quickUpload} disabled={uploading}>
                  {uploading ? "Uploading…" : "Upload"}
                </button>
              </div>
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