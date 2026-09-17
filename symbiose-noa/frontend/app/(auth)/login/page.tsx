"use client"
import { useEffect, useState } from "react"
import { signIn } from "next-auth/react"

// L'ADRESSE DE LA DERNIÈRE CONNEXION (03/09, demande de Noa : « sans resaisir
// le mail »). Cet écran ne se voit plus qu'une fois par appareil — la session
// dure ensuite d'elle-même — mais quand il se voit, l'adresse est déjà là.
// Cette préférence locale ne contient que la dernière adresse saisie.
const CLE_DERNIER_EMAIL = "pluton.dernier_email"

type State = "idle" | "loading" | "error"

export default function LoginPage() {
  const [email, setEmail] = useState("")
  const [state, setState] = useState<State>("idle")
  const [error, setError] = useState("")

  // Après le rendu, jamais pendant : lire le stockage local au premier rendu
  // ferait diverger le HTML du serveur et celui du navigateur (hydratation).
  useEffect(() => {
    try {
      const retenu = window.localStorage.getItem(CLE_DERNIER_EMAIL)
      if (retenu) setEmail(retenu)
    } catch {
      // Navigation privée, stockage refusé : l'écran marche comme avant.
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return
    setState("loading")
    setError("")

    try {
      const adresse = email.trim().toLowerCase()
      const res = await signIn("credentials", { email: adresse, redirect: false })
      if (!res || res.error || !res.ok) {
        setError("Connexion impossible. Vérifiez votre adresse ou contactez votre administrateur.")
        setState("error")
        return
      }
      try { window.localStorage.setItem(CLE_DERNIER_EMAIL, adresse) } catch { /* rien */ }
      window.location.assign("/chat")
    } catch {
      setError("Une erreur est survenue. Réessayez.")
      setState("error")
    }
  }

  const card: React.CSSProperties = {
    background: "var(--marque-surface)",
    borderRadius: "var(--marque-radius-card)",
    padding: "clamp(24px, 7vw, 40px) clamp(18px, 8vw, 48px)",
    boxShadow: "var(--marque-shadow-card)",
    textAlign: "center",
    maxWidth: 380,
    width: "100%",
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "radial-gradient(circle at 50% -10%, var(--marque-primary-subtle), transparent 55%), var(--marque-canvas)",
    }}>
      <div className="sym-in sym-card" style={card}>
        <img
          src="/symbiose-paysage.svg"
          alt="Symbiose Paysage"
          className="sym-in sym-in-1"
          style={{ width: 210, maxWidth: "85%", height: "auto", display: "block", margin: "0 auto 32px" }}
        />

        {(state === "idle" || state === "loading" || state === "error") && (
          <form className="sym-fade" onSubmit={handleSubmit}>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="votre@email.fr"
              aria-label="Adresse e-mail"
              autoComplete="email"
              disabled={state === "loading"}
              required
              className="sym-in sym-in-1"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid var(--marque-border)",
                borderRadius: "var(--marque-radius-pill)",
                fontSize: 14,
                marginBottom: 12,
                boxSizing: "border-box",
                outline: "none",
                transition: "border-color .2s ease, box-shadow .2s ease",
              }}
            />
            {error && (
              <p className="sym-pop" style={{ color: "var(--marque-error-text)", fontSize: 13, margin: "0 0 12px" }}>{error}</p>
            )}
            <button
              type="submit"
              disabled={state === "loading"}
              className="sym-tap sym-in sym-in-2"
              style={{
                width: "100%",
                padding: "12px 24px",
                background: "linear-gradient(180deg, var(--marque-primary), var(--marque-primary-hover))",
                color: "var(--marque-text-on-dark)",
                border: "none",
                borderRadius: "var(--marque-radius-pill)",
                fontSize: 14,
                fontWeight: 500,
                cursor: state === "loading" ? "not-allowed" : "pointer",
                opacity: state === "loading" ? 0.7 : 1,
                boxShadow: "var(--marque-shadow-card)",
              }}
            >
              {state === "loading" ? "Connexion..." : "Connecter"}
            </button>
          </form>
        )}

        <p className="sym-in sym-in-4" style={{ color: "var(--marque-text-muted)", fontSize: 11, margin: "24px 0 0", letterSpacing: ".04em" }}>
          Accès réservé aux collaborateurs Symbiose Paysage
        </p>
      </div>
    </div>
  )
}
