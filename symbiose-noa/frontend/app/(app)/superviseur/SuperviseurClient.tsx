"use client"
import { useEffect, useRef, useState, useCallback } from "react"

interface Props { apiUrl: string; token: string }

const POLL_MS = 3000

// Palette console (sombre, façon terminal développeur)
const C = {
  bg: "#0C130E", panel: "#121C15", panel2: "#0F1712", border: "#213026",
  text: "#CFE6D6", dim: "#6E8C77", green: "#3FD98B", amber: "#E7B84B",
  red: "#F87171", blue: "#7BB0F0", mono: "ui-monospace,'SF Mono','Cascadia Code',Menlo,Consolas,monospace",
}

async function getJSON(apiUrl: string, path: string, token: string) {
  const res = await fetch(`${apiUrl}${path}`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

function fmtTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }
  catch { return "--:--:--" }
}

export default function SuperviseurClient({ apiUrl, token }: Props) {
  const [system, setSystem] = useState<any>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [agents, setAgents] = useState<any[]>([])
  const [live, setLive] = useState(true)
  const [err, setErr] = useState<string>("")
  const [tick, setTick] = useState(0)
  const logBoxRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const [sys, act, ag] = await Promise.all([
        getJSON(apiUrl, "/api/dashboard/system", token).catch(() => null),
        getJSON(apiUrl, "/api/dashboard/activity?limit=60", token).catch(() => []),
        getJSON(apiUrl, "/api/dashboard/agents-activity", token).catch(() => []),
      ])
      if (sys) setSystem(sys)
      setLogs(Array.isArray(act) ? act : [])
      setAgents(Array.isArray(ag) ? ag : [])
      setErr("")
      setTick((t) => t + 1)
    } catch (e: any) {
      setErr(e?.message || "erreur")
    }
  }, [apiUrl, token])

  useEffect(() => {
    refresh()
    if (!live) return
    const id = setInterval(refresh, POLL_MS)
    return () => clearInterval(id)
  }, [refresh, live])

  const kpi = (label: string, value: any, color = C.text) => (
    <div style={{ background: C.panel2, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ fontSize: 10, color: C.dim, textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
      <div style={{ fontFamily: C.mono, fontSize: 16, fontWeight: 600, color, marginTop: 3 }}>{value ?? "—"}</div>
    </div>
  )

  const db = system?.db || {}

  return (
    <div style={{ minHeight: "calc(100vh - 64px)", background: C.bg, color: C.text, fontFamily: C.mono, padding: "20px 24px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 18 }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: live ? C.green : C.dim, boxShadow: live ? `0 0 8px ${C.green}` : "none" }} />
        <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.3px" }}>Console développeur</div>
        <div style={{ fontSize: 12, color: C.dim }}>super_admin · flux temps réel</div>
        <div style={{ flex: 1 }} />
        <button onClick={() => setLive((v) => !v)} style={{ fontFamily: C.mono, fontSize: 12, background: live ? C.panel : C.panel2, color: live ? C.green : C.dim, border: `1px solid ${C.border}`, borderRadius: 7, padding: "6px 12px", cursor: "pointer" }}>
          {live ? "● LIVE (pause)" : "○ figé (reprendre)"}
        </button>
        <button onClick={refresh} style={{ fontFamily: C.mono, fontSize: 12, background: C.panel2, color: C.text, border: `1px solid ${C.border}`, borderRadius: 7, padding: "6px 12px", cursor: "pointer" }}>
          ↻ refresh
        </button>
      </div>

      {err && <div style={{ color: C.red, fontSize: 12, marginBottom: 12 }}>⚠ {err}</div>}

      {/* System KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10, marginBottom: 14 }}>
        {kpi("environnement", system?.environment, C.blue)}
        {kpi("debug", String(system?.debug ?? "—"), system?.debug ? C.amber : C.dim)}
        {kpi("checkpointer", system?.checkpointer, C.green)}
        {kpi("langfuse", system?.observability?.langfuse_enabled ? "ON" : "off", system?.observability?.langfuse_enabled ? C.green : C.dim)}
        {kpi("plage horaire", system?.schedule)}
        {kpi("browser", system?.browser_enabled ? "ON" : "off", system?.browser_enabled ? C.green : C.dim)}
      </div>

      {/* DB counters */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 18 }}>
        {kpi("users actifs", db.users_actifs)}
        {kpi("threads", db.threads)}
        {kpi("audit events", db.audit_events)}
        {kpi("validations", db.validations_pending, Number(db.validations_pending) > 0 ? C.amber : C.text)}
        {kpi("skills", db.skills)}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 16 }}>
        {/* Live log stream */}
        <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 12, color: C.dim, display: "flex", justifyContent: "space-between" }}>
            <span>audit_log · {logs.length} événements</span>
            <span>maj #{tick}</span>
          </div>
          <div ref={logBoxRef} style={{ maxHeight: 460, overflowY: "auto", padding: "8px 0" }}>
            {logs.length === 0 && <div style={{ padding: 20, color: C.dim, fontSize: 12 }}>— aucun événement —</div>}
            {logs.map((l: any) => {
              const ok = l.success !== false
              return (
                <div key={l.id} style={{ display: "flex", gap: 10, padding: "4px 14px", fontSize: 12.5, borderBottom: `1px solid ${C.panel2}`, whiteSpace: "nowrap" }}>
                  <span style={{ color: C.dim }}>{fmtTime(l.created_at)}</span>
                  <span style={{ color: ok ? C.green : C.red, width: 12 }}>{ok ? "✓" : "✗"}</span>
                  <span style={{ color: C.text, minWidth: 150, fontWeight: 600 }}>{l.action}</span>
                  <span style={{ color: C.blue }}>{l.agent_id ? `[${l.agent_id}]` : ""}</span>
                  <span style={{ color: C.dim, overflow: "hidden", textOverflow: "ellipsis" }}>{l.user_id ? String(l.user_id).slice(0, 8) : "system"}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Side: providers + chains + agents */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 12, color: C.dim, marginBottom: 10 }}>fournisseurs LLM</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {system?.providers && Object.entries(system.providers).map(([p, up]: any) => (
                <span key={p} style={{ fontSize: 11, padding: "3px 8px", borderRadius: 6, background: up ? "rgba(63,217,139,0.12)" : C.panel2, color: up ? C.green : C.dim, border: `1px solid ${up ? "rgba(63,217,139,0.3)" : C.border}` }}>
                  {up ? "●" : "○"} {p}
                </span>
              ))}
            </div>
          </div>

          <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 12, color: C.dim, marginBottom: 10 }}>cascade (par palier)</div>
            {system?.chains && Object.entries(system.chains).map(([tier, list]: any) => (
              <div key={tier} style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: C.amber, textTransform: "uppercase" }}>{tier}</div>
                <div style={{ fontSize: 11, color: C.text, lineHeight: 1.5, wordBreak: "break-all" }}>
                  {(list as string[]).join(" → ") || "—"}
                </div>
              </div>
            ))}
          </div>

          <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 12, color: C.dim, marginBottom: 10 }}>agents (aujourd'hui)</div>
            {agents.length === 0 && <div style={{ fontSize: 11, color: C.dim }}>— aucune requête —</div>}
            {agents.map((a: any) => (
              <div key={a.agent_id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "3px 0" }}>
                <span style={{ color: C.blue }}>{a.agent_id}</span>
                <span style={{ color: C.dim }}>
                  {a.request_count} req · <span style={{ color: C.green }}>{a.success_count}✓</span> <span style={{ color: C.red }}>{a.failure_count}✗</span> · {a.avg_duration_ms}ms
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
