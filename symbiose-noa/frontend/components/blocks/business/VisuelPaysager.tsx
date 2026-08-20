"use client"
import { useEffect, useState } from "react"

/**
 * LE RENDU VISUEL GÉNÉRÉ, affiché dans le chat comme une planche.
 *
 * Quand l'assistant génère un visuel d'aménagement, les images sont rangées
 * côté serveur (elles ont été payées, elles ne dépendent plus d'un CDN
 * externe) et le modèle insère ce bloc avec leurs clés. Chargées avec le
 * jeton de session (une balise <img> ne porte pas d'en-tête d'autorisation),
 * affichées en planche, cliquables pour l'échelle 1. Le bandeau dit ce que
 * c'est — une ILLUSTRATION d'intention, pas une simulation du terrain réel —
 * parce que cette confusion-là se paie en rendez-vous client.
 */
type ImageVisuel = { cle?: string; url?: string; legende?: string }

function Image({ image, apiUrl, backendToken }: { image: ImageVisuel; apiUrl?: string; backendToken?: string }) {
  const [src, setSrc] = useState<string | null>(image.url || null)
  const [etat, setEtat] = useState<"charge" | "pret" | "absent">(image.url ? "pret" : image.cle ? "charge" : "absent")

  useEffect(() => {
    if (!image.cle || !apiUrl) return
    let vivant = true
    let objet: string | null = null
    fetch(`${apiUrl}/api/visuels/${encodeURIComponent(image.cle)}`,
          { headers: backendToken ? { Authorization: `Bearer ${backendToken}` } : {}, cache: "force-cache" })
      .then(async (r) => { if (!r.ok) throw new Error(String(r.status)); return r.blob() })
      .then((b) => { if (!vivant) return; objet = URL.createObjectURL(b); setSrc(objet); setEtat("pret") })
      .catch(() => { if (vivant) setEtat("absent") })
    return () => { vivant = false; if (objet) URL.revokeObjectURL(objet) }
  }, [image.cle, apiUrl, backendToken])

  const ouvrir = () => { if (src) window.open(src, "_blank", "noopener") }

  return (
    <figure style={{ margin: 0, borderRadius: 14, overflow: "hidden", background: "var(--marque-primary-subtle)",
                     position: "relative", aspectRatio: "16 / 10", cursor: src ? "zoom-in" : "default" }}
            onClick={ouvrir} title={src ? "Ouvrir en grand" : undefined}>
      {etat === "pret" && src && (
        <img src={src} alt={image.legende || "Visuel d'aménagement paysager"}
             style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
      )}
      {etat === "charge" && <div className="sym-skeleton" style={{ position: "absolute", inset: 0 }} />}
      {etat === "absent" && (
        <figcaption style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center",
                             color: "var(--marque-text-muted)", fontSize: 12.5, padding: 12, textAlign: "center" }}>
          Visuel indisponible (supprimé ou expiré)
        </figcaption>
      )}
    </figure>
  )
}

export function VisuelPaysager({
  titre, images = [], apiUrl, backendToken,
}: { titre?: string; images?: ImageVisuel[]; apiUrl?: string; backendToken?: string }) {
  const liste = images.filter((i) => i && (i.cle || i.url))
  return (
    <div className="sym-card" style={{ maxWidth: 640, borderRadius: "var(--marque-radius-card)", overflow: "hidden",
                                        background: "var(--marque-surface)", border: "1px solid var(--marque-border)",
                                        boxShadow: "var(--marque-shadow-card)" }}>
      <div style={{ padding: "12px 16px 10px", display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
        <div style={{ fontWeight: 700, fontSize: 14.5, color: "var(--marque-text-primary)" }}>{titre || "Visuel d'aménagement"}</div>
        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--marque-text-muted)", whiteSpace: "nowrap" }}>généré par IA</span>
      </div>
      <div style={{ display: "grid", gap: 6, padding: "0 10px",
                    gridTemplateColumns: liste.length > 1 ? "1fr 1fr" : "1fr" }}>
        {liste.map((img, i) => <Image key={img.cle || img.url || i} image={img} apiUrl={apiUrl} backendToken={backendToken} />)}
        {liste.length === 0 && <div style={{ padding: 24, textAlign: "center", color: "var(--marque-text-muted)", fontSize: 13 }}>Aucune image.</div>}
      </div>
      <div style={{ padding: "9px 16px 12px", fontSize: 11.5, color: "var(--marque-text-muted)", lineHeight: 1.45 }}>
        Illustration d'intention d'aménagement, générée à partir d'une description — ce n'est ni un plan
        ni une simulation du terrain réel.
      </div>
    </div>
  )
}
