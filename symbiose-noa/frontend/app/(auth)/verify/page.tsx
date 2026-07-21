"use client"
import { Suspense, useEffect, useRef, useState } from "react"
import { signIn } from "next-auth/react"
import { useSearchParams } from "next/navigation"

function VerifyContent() {
  const params = useSearchParams()
  const [status, setStatus] = useState<"loading" | "error">("loading")
  // Le lien est à usage unique : on garantit un SEUL appel de vérification,
  // même avec le double-rendu de React en dev (sinon le token est consommé 2×).
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    const token = params.get("token")
    const email = params.get("email")

    if (!token || !email) {
      setStatus("error")
      return
    }
    started.current = true

    signIn("credentials", { token, email, redirect: false }).then((res) => {
      if (res?.error) {
        setStatus("error")
      } else {
        window.location.href = "/chat"
      }
    })
  }, [params])

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--color-canvas)",
    }}>
      <div style={{
        background: "var(--color-surface)",
        borderRadius: "var(--radius-card)",
        padding: "40px 48px",
        boxShadow: "var(--shadow-card)",
        textAlign: "center",
        maxWidth: 380,
      }}>
        <div style={{ fontSize: 32, marginBottom: 16 }}>🌿</div>
        {status === "loading" ? (
          <>
            <p style={{ fontWeight: 500, margin: "0 0 8px", color: "var(--color-text-primary)" }}>Connexion en cours...</p>
            <p style={{ color: "var(--color-text-muted)", fontSize: 13, margin: 0 }}>Vous allez être redirigé automatiquement.</p>
          </>
        ) : (
          <>
            <p style={{ fontWeight: 500, margin: "0 0 8px", color: "var(--color-error-text)" }}>Lien invalide ou expiré</p>
            <p style={{ color: "var(--color-text-muted)", fontSize: 13, margin: "0 0 20px" }}>
              Le lien a peut-être déjà été utilisé ou a expiré (15 min).
            </p>
            <a href="/login" style={{
              display: "inline-block",
              background: "var(--color-primary)",
              color: "var(--color-text-on-dark)",
              padding: "10px 20px",
              borderRadius: "var(--radius-pill)",
              textDecoration: "none",
              fontSize: 14,
              fontWeight: 500,
            }}>
              Demander un nouveau lien
            </a>
          </>
        )}
      </div>
    </div>
  )
}

export default function VerifyPage() {
  return (
    <Suspense>
      <VerifyContent />
    </Suspense>
  )
}
