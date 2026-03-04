"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, type EvidenceItem, type ShareLink, type ShareLinkItem } from "@/lib/api";

function fmt(ts?: string | null) {
  if (!ts) return "-";
  try {
    return new Date(ts).toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return ts;
  }
}

export default function ShareLinksPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const [links, setLinks] = useState<ShareLink[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);

  const [selectedLinkId, setSelectedLinkId] = useState<string>("");
  const selectedLink = useMemo(() => links.find((l) => l.id === selectedLinkId) ?? null, [links, selectedLinkId]);

  const [items, setItems] = useState<ShareLinkItem[]>([]);
  const itemEvidenceIds = useMemo(() => new Set(items.map((i) => i.evidence_id)), [items]);

  // Create link form
  const [newName, setNewName] = useState("Vendor Pack");
  const [expiresDays, setExpiresDays] = useState<number>(14);
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [createdUrl, setCreatedUrl] = useState<string | null>(null);

  async function loadAll() {
    setErr("");
    setLoading(true);
    try {
      const [ls, ev] = await Promise.all([api.listShareLinks(), api.listEvidence()]);
      setLinks(ls ?? []);
      setEvidence((ev ?? []).filter((x) => !("deleted_at" in (x as any) && (x as any).deleted_at))); // defensive
      if (!selectedLinkId && ls?.length) {
        setSelectedLinkId(ls[0].id);
      }
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadItems(linkId: string) {
    setErr("");
    try {
      const it = await api.listShareLinkItems(linkId);
      setItems(it ?? []);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setItems([]);
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

  useEffect(() => {
    if (!selectedLinkId) return;
    loadItems(selectedLinkId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLinkId]);

  async function createLink() {
    setErr("");
    setCreatedToken(null);
    setCreatedUrl(null);
    try {
      const exp =
        expiresDays > 0 ? new Date(Date.now() + expiresDays * 24 * 60 * 60 * 1000).toISOString() : null;

      const r = await api.createShareLink({
        name: newName.trim() || "Share Link",
        expires_at: exp,
        policy_version: "v1",
        settings: {},
      });

      // refresh
      await loadAll();

      // best-effort show token/url if returned
      const token = (r as any)?.token ?? null;
      const url = (r as any)?.public_url ?? (r as any)?.url ?? null;
      setCreatedToken(token);
      setCreatedUrl(url);

      if (r?.id) setSelectedLinkId(r.id);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function revokeSelected() {
    if (!selectedLinkId) return;
    setErr("");
    try {
      await api.revokeShareLink(selectedLinkId);
      await loadAll();
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  async function toggleEvidence(evId: string, checked: boolean) {
    if (!selectedLinkId) return;
    setErr("");
    try {
      if (checked) {
        await api.addShareLinkItem(selectedLinkId, evId);
      } else {
        await api.removeShareLinkItem(selectedLinkId, evId);
      }
      await loadItems(selectedLinkId);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 28, margin: 0 }}>Share Links</h1>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={() => router.push("/dashboard")}>Dashboard</button>
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

      {loading && <p>Loading…</p>}

      {!loading && err && (
        <div style={{ padding: 12, background: "#fee", border: "1px solid #f99", marginTop: 16 }}>
          <b>Error:</b> {err}
        </div>
      )}

      {!loading && (
        <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 16, marginTop: 16 }}>
          {/* Left: link list + create */}
          <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 14 }}>
            <h2 style={{ marginTop: 0 }}>Create</h2>
            <div style={{ display: "grid", gap: 10 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span>Name</span>
                <input value={newName} onChange={(e) => setNewName(e.target.value)} />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Expires (days)</span>
                <input
                  type="number"
                  min={0}
                  max={365}
                  value={expiresDays}
                  onChange={(e) => setExpiresDays(parseInt(e.target.value || "0", 10))}
                />
              </label>

              <button onClick={createLink}>Create Share Link</button>

              {(createdToken || createdUrl) && (
                <div style={{ background: "#f7f7f7", padding: 10, borderRadius: 8, fontSize: 12 }}>
                  <div style={{ marginBottom: 6 }}>
                    <b>Created!</b> Save this now (token may be shown once).
                  </div>
                  {createdUrl && (
                    <div style={{ marginBottom: 6 }}>
                      <div>Public URL:</div>
                      <code style={{ wordBreak: "break-all" }}>{createdUrl}</code>
                    </div>
                  )}
                  {createdToken && (
                    <div>
                        <div>Public URL:</div>
                        <code style={{ wordBreak: "break-all" }}>
                        {typeof window !== "undefined" ? `${window.location.origin}/share/${createdToken}` : `/share/${createdToken}`}
                        </code>

                        <div style={{ marginTop: 8, display: "flex", gap: 10, flexWrap: "wrap" }}>
                        <button
                            onClick={() => {
                            const url =
                                typeof window !== "undefined"
                                ? `${window.location.origin}/share/${createdToken}`
                                : `/share/${createdToken}`;
                            navigator.clipboard.writeText(url);
                            }}
                        >
                            Copy URL
                        </button>

                        <button
                            onClick={() => {
                            const url =
                                typeof window !== "undefined"
                                ? `${window.location.origin}/share/${createdToken}`
                                : `/share/${createdToken}`;
                            window.open(url, "_blank", "noopener,noreferrer");
                            }}
                        >
                            Open
                        </button>
                        </div>
                    </div>
                    )}
                </div>
              )}
            </div>

            <hr style={{ margin: "16px 0" }} />

            <h2 style={{ marginTop: 0 }}>Links</h2>
            {links.length === 0 ? (
              <p>No share links yet.</p>
            ) : (
              <div style={{ display: "grid", gap: 8 }}>
                {links.map((l) => (
                  <button
                    key={l.id}
                    style={{
                      textAlign: "left",
                      padding: 10,
                      borderRadius: 8,
                      border: l.id === selectedLinkId ? "2px solid #333" : "1px solid #ddd",
                      background: "#fff",
                    }}
                    onClick={() => setSelectedLinkId(l.id)}
                  >
                    <div style={{ fontWeight: 600 }}>{l.name ?? l.id}</div>
                    <div style={{ fontSize: 12, color: "#666" }}>
                      created: {fmt(l.created_at)} · expires: {fmt(l.expires_at)} · revoked: {fmt(l.revoked_at)}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          {/* Right: evidence selection for selected link */}
          <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
              <h2 style={{ marginTop: 0 }}>Attach Evidence</h2>
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => loadItems(selectedLinkId)} disabled={!selectedLinkId}>
                  Refresh Items
                </button>
                <button onClick={revokeSelected} disabled={!selectedLinkId}>
                  Revoke Link
                </button>
              </div>
            </div>

            {!selectedLink ? (
              <p>Select a share link on the left.</p>
            ) : (
              <>
                <div style={{ marginBottom: 10, fontSize: 13, color: "#444" }}>
                  <b>Selected:</b> {selectedLink.name} <span style={{ color: "#777" }}>({selectedLink.id})</span>
                </div>

                {evidence.length === 0 ? (
                  <p>No evidence available (upload evidence first).</p>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left", padding: 8, borderBottom: "1px solid #ddd" }}>Include</th>
                        <th style={{ textAlign: "left", padding: 8, borderBottom: "1px solid #ddd" }}>Title</th>
                        <th style={{ textAlign: "left", padding: 8, borderBottom: "1px solid #ddd" }}>Category</th>
                        <th style={{ textAlign: "left", padding: 8, borderBottom: "1px solid #ddd" }}>Tags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evidence.map((ev) => {
                        const checked = itemEvidenceIds.has(ev.id);
                        const cat = (ev as any).category ?? "-";
                        const tags = Array.isArray((ev as any).tags) ? (ev as any).tags.join(", ") : "";
                        return (
                          <tr key={ev.id}>
                            <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(e) => toggleEvidence(ev.id, e.target.checked)}
                              />
                            </td>
                            <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>
                              {ev.title ?? ev.original_filename ?? ev.id}
                            </td>
                            <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{cat}</td>
                            <td style={{ padding: 8, borderBottom: "1px solid #eee" }}>{tags}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}

                <div style={{ marginTop: 12, fontSize: 12, color: "#666" }}>
                  Tip: Create a link, then check evidence items to include in the shared pack.
                </div>

                <div style={{ marginTop: 16 }}>
                  <button onClick={() => router.push("/evidence")}>Open Evidence Library</button>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}