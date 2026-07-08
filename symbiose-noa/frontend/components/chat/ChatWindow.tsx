"use client"
import { useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"
import MessageList from "./MessageList"
import InputBar from "./InputBar"
import { apiRequest } from "@/lib/api"
import { openChatSocket, sendQuery, ChatEvent } from "@/lib/ws"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
}

interface ChatWindowProps {
  threadId?: string | null
  token?: string        // passé côté serveur (fiable) ; sinon repli sur useSession
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

// Au-delà de ce délai sans le moindre événement WS, on bascule sur le POST.
const WS_STALL_MS = 6000

export default function ChatWindow({ threadId: initialThreadId = null, token: tokenProp }: ChatWindowProps) {
  const { data: session } = useSession()
  const token = tokenProp || (session as any)?.backendToken
  const [messages, setMessages] = useState<Message[]>([])
  const [threadId, setThreadId] = useState<string | null>(initialThreadId)
  const [loading, setLoading] = useState(false)
  const [thinkingNode, setThinkingNode] = useState<string | null>(null)
  const [pendingValidation, setPendingValidation] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!initialThreadId || !token) return
    apiRequest<any[]>(`/api/chat/threads/${initialThreadId}/messages`, { token })
      .then((rows) =>
        setMessages(
          (rows || []).map((m) => ({
            id: String(m.id),
            role: m.role === "assistant" ? "assistant" : "user",
            content: m.content ?? "",
          }))
        )
      )
      .catch(() => {})
  }, [initialThreadId, token])

  useEffect(() => () => { try { wsRef.current?.close() } catch { /* no-op */ } }, [])

  const sendMessage = (text: string) => {
    setMessages((prev) => [...prev, { id: newId(), role: "user", content: text }])
    setLoading(true)
    setThinkingNode(null)
    setPendingValidation(false)

    const tid = threadId ?? newId()
    if (!threadId) setThreadId(tid)

    const pushAssistant = (content: string) =>
      setMessages((prev) => [...prev, { id: newId(), role: "assistant", content }])

    if (!token) {
      pushAssistant("Erreur : session expirée, veuillez vous reconnecter.")
      setLoading(false)
      return
    }

    let settled = false
    let stallTimer: ReturnType<typeof setTimeout> | null = null
    const clearStall = () => { if (stallTimer) { clearTimeout(stallTimer); stallTimer = null } }
    const closeWs = () => { try { wsRef.current?.close() } catch { /* no-op */ } }

    const finish = (assistantContent: string | null, isPending: boolean) => {
      if (settled) return
      settled = true
      clearStall()
      setThinkingNode(null)
      if (isPending) setPendingValidation(true)
      else if (assistantContent !== null) pushAssistant(assistantContent)
      setLoading(false)
      closeWs()
    }

    // Repli POST /api/chat/ — chemin fiable et vérifié.
    const fallbackPost = async () => {
      if (settled) return
      settled = true
      clearStall()
      closeWs()
      try {
        const res = await apiRequest<{ response: string; thread_id: string; status?: string; validation_id?: string | null }>(
          "/api/chat/",
          { method: "POST", token, body: JSON.stringify({ query: text, thread_id: tid }) }
        )
        if (res.thread_id) setThreadId(res.thread_id)
        const needsValidation =
          res.status === "pending_validation" || res.status === "validation_required" || Boolean(res.validation_id)
        if (needsValidation) setPendingValidation(true)
        else pushAssistant(res.response ?? "")
      } catch (err: any) {
        pushAssistant(`Erreur : ${err?.message ?? "requête impossible"}`)
      } finally {
        setThinkingNode(null)
        setLoading(false)
      }
    }

    // Tente le streaming WebSocket ; garde-fou anti-blocage → POST.
    try {
      openChatSocket(tid, token, {
        onOpen: () => sendQuery(wsRef.current!, text, false),
        onEvent: (event: ChatEvent) => {
          clearStall()  // le WS répond → on annule le repli anti-blocage
          const t = event.type
          if (t === "final" || (t === undefined && event.response !== undefined)) {
            finish(event.response ?? "", false)
          } else if (t === "validation_required" || t === "pending_validation") {
            finish(null, true)
          } else if (t === "error") {
            fallbackPost()
          } else if (t === "node" || event.node !== undefined) {
            setThinkingNode(String(event.node ?? (event.data && event.data.node) ?? ""))
          }
        },
        onError: () => fallbackPost(),
        onClose: () => { if (!settled) fallbackPost() },
      })
        .then((ws) => { wsRef.current = ws })
        .catch(() => fallbackPost())
      // Si aucun événement n'arrive (WS bloqué / injoignable), on bascule sur POST.
      stallTimer = setTimeout(() => { if (!settled) fallbackPost() }, WS_STALL_MS)
    } catch {
      fallbackPost()
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 64px)" }}>
      <MessageList messages={messages} />

      {loading && (
        <div style={{ padding: "6px 32px", fontSize: 13, color: "var(--color-text-muted)", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--color-primary-mid)", display: "inline-block" }} />
          Symbiose réfléchit…{thinkingNode ? ` (${thinkingNode})` : ""}
        </div>
      )}

      {pendingValidation && (
        <div style={{ margin: "8px 32px", padding: "12px 16px", background: "var(--color-pending-bg)", color: "var(--color-pending-text)", borderRadius: 10, fontSize: 13, fontWeight: 600 }}>
          ⏳ En attente de validation humaine
        </div>
      )}

      <InputBar onSend={sendMessage} disabled={loading} />
    </div>
  )
}
