"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [msg, setMsg] = useState("Checking session…");

  useEffect(() => {
    let cancelled = false;

    async function go() {
      const token = getToken();

      if (!token) {
        router.replace("/login");
        return;
      }

      try {
        // Validate token by calling /me
        await api.me();
        if (!cancelled) router.replace("/dashboard");
      } catch {
        // Token exists but is invalid/expired or secret changed
        clearToken();
        if (!cancelled) {
          setMsg("Session expired. Redirecting to login…");
          router.replace("/login");
        }
      }
    }

    go();

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div style={{ padding: 40 }}>
      <h1>securitypassport</h1>
      <p>{msg}</p>
    </div>
  );
}