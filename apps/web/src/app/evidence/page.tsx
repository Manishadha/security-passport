"use client";

import { useEffect, useMemo, useState } from "react";
import { api, clearToken, type EvidenceItem } from "@/lib/api";
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

function fmtBytes(n?: number | null) {
  if (n == null) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let x = n;
  let i = 0;
  while (x >= 1024 && i < units.length - 1) {
    x /= 1024;
    i += 1;
  }
  return `${x.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

type EditState = {
  open: boolean;
  item: EvidenceItem | null;
  title: string;
  description: string;
  category: string;
  tagsCsv: string;
};

export default function EvidencePage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const [items, setItems] = useState<EvidenceItem[]>([]);
  const [includeDeleted, setIncludeDeleted] = useState(false);

  const [limit, setLimit] = useState(20);
  const [offset, setOffset] = useState(0);

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const [edit, setEdit] = useState<EditState>({
    open: false,
    item: null,
    title: "",
    description: "",
    category: "",
    tagsCsv: "",
  });

  const page = useMemo(() => Math.floor(offset / limit) + 1, [offset, limit]);

  async function load() {
    setErr("");
    setLoading(true);
    try {
      const data = await api.listEvidencePaged({ limit, offset, include_deleted: includeDeleted });
      setItems(data ?? []);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!localStorage.getItem("sp_token")) {
      router.push("/login");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit, offset, includeDeleted]);

  function openEdit(item: EvidenceItem) {
    setEdit({
      open: true,
      item,
      title: item.title ?? "",
      description: (item.description ?? "") as string,
      category: (item.category ?? "") as string,
      tagsCsv: (item.tags ?? []).join(", "),
    });
  }

  function closeEdit() {
    setEdit({ open: false, item: null, title: "", description: "", category: "", tagsCsv: "" });
  }

  async function saveEdit() {
    if (!edit.item) return;
    setErr("");

    try {
      const tags = edit.tagsCsv
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      // PATCH returns { ok, changed } now — not the updated item
      await api.patchEvidence(edit.item.id, {
        title: edit.title.trim() || edit.item.title,
        description: edit.description.trim() || null,
        category: edit.category.trim() || null,
        tags,
      });

      // Fetch the real updated record
      const updated = await api.getEvidence(edit.item.id);

      setItems((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      closeEdit();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function doDelete(item: EvidenceItem) {
    if (!confirm("Soft-delete this evidence item?")) return;
    setErr("");
    try {
      await api.deleteEvidence(item.id);
      // reload to respect includeDeleted toggle
      await load();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function doDownload(item: EvidenceItem) {
    setErr("");
    try {
      const dl = await api.getEvidenceDownloadUrl(item.id);
      await downloadWithAuth(dl.url, item.original_filename || `${item.id}.bin`);
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

    setUploading(true);
    try {
      // Create record (title will match filename; backend also has fallback)
      const created = await api.createEvidence({
        title: file.name,
        original_filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        tags: [],
        category: null,
      });

      await api.uploadEvidenceFile(created.id, file);

      setFile(null);
      setOffset(0);
      await load();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 28, marginBottom: 6 }}>Evidence</h1>
          <div style={{ fontSize: 13, color: "#666" }}>
            Upload, tag, edit metadata, download, and soft-delete evidence items.
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button onClick={() => router.push("/dashboard")}>Back to Dashboard</button>
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

      {err && (
        <div style={{ padding: 12, background: "#fee", border: "1px solid #f99", marginTop: 16 }}>
          <b>Error:</b> {err}
        </div>
      )}

      <section style={{ padding: 16, border: "1px solid #ddd", borderRadius: 8, marginTop: 16 }}>
        <h2 style={{ marginTop: 0 }}>Upload</h2>

        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button onClick={doUpload} disabled={uploading}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </section>

      <section style={{ padding: 16, border: "1px solid #ddd", borderRadius: 8, marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ marginTop: 0 }}>Library</h2>

          <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={includeDeleted}
                onChange={(e) => {
                  setOffset(0);
                  setIncludeDeleted(e.target.checked);
                }}
              />
              <span>Include deleted</span>
            </label>

            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>Page size</span>
              <select
                value={limit}
                onChange={(e) => {
                  setOffset(0);
                  setLimit(parseInt(e.target.value, 10));
                }}
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
            </label>

            <button onClick={load} disabled={loading}>
              {loading ? "Loading…" : "Refresh"}
            </button>
          </div>
        </div>

        <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 13, color: "#666" }}>
            Showing {items.length} item(s). Page {page}.
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0 || loading}
            >
              Prev
            </button>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={items.length < limit || loading}
            >
              Next
            </button>
          </div>
        </div>

        <div style={{ marginTop: 12 }}>
          {items.length === 0 ? (
            <p>No evidence found.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Title</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Category</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Tags</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Created</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Uploaded</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Size</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Status</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #ddd", padding: 8 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((ev) => {
                  const deleted = Boolean(ev.deleted_at);
                  const uploaded = Boolean(ev.uploaded_at) && Boolean(ev.storage_key);

                  return (
                    <tr key={ev.id} style={{ opacity: deleted ? 0.55 : 1 }}>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                        <div style={{ fontWeight: 600 }}>{ev.title || ev.original_filename || ev.id}</div>
                        <div style={{ fontSize: 12, color: "#666" }}>{ev.description || ""}</div>
                      </td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{ev.category || "-"}</td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                        {(ev.tags ?? []).length ? (ev.tags ?? []).join(", ") : "-"}
                      </td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                        {ev.created_at ? new Date(ev.created_at).toLocaleString() : "-"}
                      </td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                        {uploaded ? new Date(ev.uploaded_at as string).toLocaleString() : "-"}
                      </td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>{fmtBytes(ev.size_bytes)}</td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                        {deleted ? "deleted" : uploaded ? "ready" : "pending upload"}
                      </td>
                      <td style={{ borderBottom: "1px solid #eee", padding: 8 }}>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <button onClick={() => openEdit(ev)} disabled={deleted}>
                            Edit
                          </button>
                          <button onClick={() => doDownload(ev)} disabled={deleted || !uploaded}>
                            Download
                          </button>
                          <button onClick={() => doDelete(ev)} disabled={deleted}>
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {edit.open && edit.item && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.35)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
          onClick={closeEdit}
        >
          <div
            style={{ background: "white", width: "min(700px, 100%)", borderRadius: 10, padding: 16 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
              <h3 style={{ marginTop: 0, marginBottom: 10 }}>Edit Evidence</h3>
              <button onClick={closeEdit}>Close</button>
            </div>

            <div style={{ display: "grid", gap: 10 }}>
              <label>
                <div style={{ fontSize: 12, color: "#666" }}>Title</div>
                <input
                  style={{ width: "100%", padding: 8 }}
                  value={edit.title}
                  onChange={(e) => setEdit((s) => ({ ...s, title: e.target.value }))}
                />
              </label>

              <label>
                <div style={{ fontSize: 12, color: "#666" }}>Category</div>
                <input
                  style={{ width: "100%", padding: 8 }}
                  value={edit.category}
                  onChange={(e) => setEdit((s) => ({ ...s, category: e.target.value }))}
                />
              </label>

              <label>
                <div style={{ fontSize: 12, color: "#666" }}>Tags (comma-separated)</div>
                <input
                  style={{ width: "100%", padding: 8 }}
                  value={edit.tagsCsv}
                  onChange={(e) => setEdit((s) => ({ ...s, tagsCsv: e.target.value }))}
                />
              </label>

              <label>
                <div style={{ fontSize: 12, color: "#666" }}>Description</div>
                <textarea
                  style={{ width: "100%", padding: 8, minHeight: 90 }}
                  value={edit.description}
                  onChange={(e) => setEdit((s) => ({ ...s, description: e.target.value }))}
                />
              </label>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 14 }}>
              <button onClick={closeEdit}>Cancel</button>
              <button onClick={saveEdit}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}