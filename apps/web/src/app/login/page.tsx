"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState("test@local.dev");
  const [password, setPassword] = useState("Password123!");
  const [msg, setMsg] = useState("");

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");

    try {
      const r = await api.login(email, password);
      setToken(r.access_token);

      // sanity: confirm it actually stored
      const saved = localStorage.getItem("sp_token");
      if (!saved) throw new Error("Token not saved to localStorage");

      setMsg("Login successful");
      router.push("/dashboard");
    } catch (e: any) {
      setMsg(e?.message ?? String(e));
    }
  }

  return (
    <div style={{ padding: 40 }}>
      <h1>Login</h1>

      <form onSubmit={login}>
        <input value={email} onChange={(e) => setEmail(e.target.value)} />
        <br />
        <br />

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <br />
        <br />

        <button type="submit">Login</button>
      </form>

      <p>{msg}</p>
    </div>
  );
}
