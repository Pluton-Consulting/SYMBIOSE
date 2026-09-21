"use client"
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { DownloadIcon, ImagePlusIcon, PencilIcon, Trash2Icon, Undo2Icon, XIcon } from "lucide-react"

/**
 * ANNOTER UNE IMAGE SANS QUITTER LE CHAT (21/09, demande de Noa).
 *
 * Pour montrer à l'assistant OÙ poser un muret ou jusqu'où élargir une allée, il
 * fallait télécharger l'image, la dessiner dans Paint, l'enregistrer, puis la
 * rejoindre au message. Un trait tracé à la main se lit pourtant mieux qu'une
 * phrase : le premier rendu de la berlinoise, guidé par un trait bleu, était
 * juste du premier coup — trois demandes « élargis le couloir », en mots, n'ont
 * rien changé.
 *
 * Le crayon ouvre l'image en grand. On dessine avec l'une des cinq couleurs, on
 * annule le dernier trait, puis on TÉLÉCHARGE l'image annotée ou on la REJOINT à
 * la conversation : elle arrive dans la barre de saisie comme n'importe quelle
 * pièce jointe, il ne reste qu'à écrire la demande.
 *
 * LES TRAITS SONT GARDÉS EN COORDONNÉES DE L'IMAGE (0 à 1), pas de l'écran : le
 * même dessin se rend à l'écran à la taille de la fenêtre, puis s'exporte à la
 * résolution réelle de l'image, sans décalage ni flou. L'épaisseur suit la
 * largeur de l'image pour la même raison.
 *
 * LE DESSIN VIT DANS UN PORTAIL, sur `document.body` : le chat est posé dans une
 * scène transformée (`transform`, cf. Scene.tsx), et un `position: fixed` à
 * l'intérieur d'un ancêtre transformé ne couvre que cet ancêtre.
 */

/** L'événement qui porte une image annotée jusqu'à la barre de saisie (InputBar). */
export const EVENEMENT_JOINDRE = "sym:joindre-fichiers"
export type DetailJoindre = { fichiers: File[]; recu?: boolean }

const COULEURS = [
  { nom: "Rouge", valeur: "#E53935" },
  { nom: "Jaune", valeur: "#FDD835" },
  { nom: "Vert", valeur: "#43A047" },
  { nom: "Bleu", valeur: "#1E88E5" },
  { nom: "Blanc", valeur: "#FFFFFF" },
] as const

/** Épaisseur d'un trait, en part de la largeur de l'image. */
const EPAISSEUR = 0.007
/** Au-delà, l'image exportée est réduite : une pièce jointe est bornée à 10 Mo. */
const COTE_MAX_EXPORT = 3000

type Trait = { couleur: string; points: [number, number][] }

/** Un nom de fichier lisible : « photo-annotee.jpg », jamais une clé. */
export function nomAnnote(nom: string | undefined): string {
  const base = (nom || "image")
    .replace(/\.[a-z0-9]{2,5}$/i, "")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "image"
  return `${base}-annotee.jpg`
}

/** Dessine les traits sur un contexte de `largeur` × `hauteur` pixels. */
export function dessinerTraits(ctx: CanvasRenderingContext2D, traits: Trait[], largeur: number, hauteur: number) {
  ctx.lineCap = "round"
  ctx.lineJoin = "round"
  ctx.lineWidth = Math.max(2, largeur * EPAISSEUR)
  for (const t of traits) {
    if (!t.points.length) continue
    ctx.strokeStyle = t.couleur
    ctx.fillStyle = t.couleur
    if (t.points.length === 1) {
      // Un simple clic laisse un point, pas rien.
      const [x, y] = t.points[0]
      ctx.beginPath()
      ctx.arc(x * largeur, y * hauteur, ctx.lineWidth / 2, 0, Math.PI * 2)
      ctx.fill()
      continue
    }
    ctx.beginPath()
    ctx.moveTo(t.points[0][0] * largeur, t.points[0][1] * hauteur)
    for (const [x, y] of t.points.slice(1)) ctx.lineTo(x * largeur, y * hauteur)
    ctx.stroke()
  }
}

function Annotateur({ src, nom, surFermer, surUtiliser }: {
  src: string
  nom?: string
  surFermer: () => void
  /** Sans ce rappel, l'image annotée rejoint la barre de saisie du chat. */
  surUtiliser?: (fichier: File) => void
}) {
  const [couleur, setCouleur] = useState<string>(COULEURS[0].valeur)
  const [traits, setTraits] = useState<Trait[]>([])
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [erreur, setErreur] = useState("")
  const [taille, setTaille] = useState<{ l: number; h: number } | null>(null)
  const zoneRef = useRef<HTMLDivElement | null>(null)
  const toileRef = useRef<HTMLCanvasElement | null>(null)
  const enCours = useRef<Trait | null>(null)
  const redessin = useRef<number | null>(null)

  // L'image elle-même. Une adresse externe se charge en « anonymous » : sans
  // cela le canevas serait « souillé » et refuserait l'export.
  useEffect(() => {
    const img = new window.Image()
    if (/^https?:/i.test(src)) img.crossOrigin = "anonymous"
    img.onload = () => setImage(img)
    img.onerror = () => setErreur("L'image n'a pas pu être ouverte.")
    img.src = src
  }, [src])

  // L'image tient dans la zone, proportions gardées (comme `object-fit: contain`).
  useLayoutEffect(() => {
    const zone = zoneRef.current
    if (!zone || !image) return
    const ajuster = () => {
      const r = zone.getBoundingClientRect()
      const ratio = image.naturalWidth / image.naturalHeight
      let l = r.width, h = r.width / ratio
      if (h > r.height) { h = r.height; l = h * ratio }
      setTaille({ l: Math.max(1, Math.floor(l)), h: Math.max(1, Math.floor(h)) })
    }
    ajuster()
    const obs = new ResizeObserver(ajuster)
    obs.observe(zone)
    return () => obs.disconnect()
  }, [image])

  const peindre = useCallback(() => {
    const toile = toileRef.current
    if (!toile || !image || !taille) return
    const dpr = window.devicePixelRatio || 1
    const l = Math.round(taille.l * dpr), h = Math.round(taille.h * dpr)
    if (toile.width !== l || toile.height !== h) { toile.width = l; toile.height = h }
    const ctx = toile.getContext("2d")
    if (!ctx) return
    ctx.clearRect(0, 0, l, h)
    ctx.drawImage(image, 0, 0, l, h)
    dessinerTraits(ctx, enCours.current ? [...traits, enCours.current] : traits, l, h)
  }, [image, taille, traits])

  useEffect(() => { peindre() }, [peindre])

  // Un repeint par image affichée, pas un par mouvement de souris.
  const demanderRepeint = () => {
    if (redessin.current != null) return
    redessin.current = requestAnimationFrame(() => { redessin.current = null; peindre() })
  }
  useEffect(() => () => { if (redessin.current != null) cancelAnimationFrame(redessin.current) }, [])

  const point = (e: React.PointerEvent<HTMLCanvasElement>): [number, number] => {
    const r = e.currentTarget.getBoundingClientRect()
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
            Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]
  }

  const surAppui = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0 && e.pointerType === "mouse") return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    enCours.current = { couleur, points: [point(e)] }
    demanderRepeint()
  }
  const surMouvement = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const t = enCours.current
    if (!t) return
    // Les points intermédiaires d'un stylet ou d'un doigt rapide : sans eux,
    // un trait vif devient une ligne brisée.
    const lot = typeof e.nativeEvent.getCoalescedEvents === "function"
      ? e.nativeEvent.getCoalescedEvents() : []
    if (lot.length) {
      const r = e.currentTarget.getBoundingClientRect()
      for (const c of lot) {
        t.points.push([Math.min(1, Math.max(0, (c.clientX - r.left) / r.width)),
                       Math.min(1, Math.max(0, (c.clientY - r.top) / r.height))])
      }
    } else {
      t.points.push(point(e))
    }
    demanderRepeint()
  }
  const surRelache = () => {
    const t = enCours.current
    enCours.current = null
    if (t) setTraits((prev) => [...prev, t])
  }

  const annuler = useCallback(() => setTraits((prev) => prev.slice(0, -1)), [])

  // Échap ferme, Ctrl/Cmd + Z annule le dernier trait. Le défilement de la
  // page est bloqué tant que l'image est ouverte : sur téléphone, dessiner
  // faisait défiler le chat derrière.
  useEffect(() => {
    const clavier = (e: KeyboardEvent) => {
      if (e.key === "Escape") surFermer()
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); annuler() }
    }
    window.addEventListener("keydown", clavier)
    const avant = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => { window.removeEventListener("keydown", clavier); document.body.style.overflow = avant }
  }, [surFermer, annuler])

  /** L'image annotée à SA résolution (bornée), en JPEG : une photo n'a pas de transparence. */
  const exporter = async (): Promise<File | null> => {
    if (!image) return null
    const echelle = Math.min(1, COTE_MAX_EXPORT / Math.max(image.naturalWidth, image.naturalHeight))
    const l = Math.round(image.naturalWidth * echelle), h = Math.round(image.naturalHeight * echelle)
    const toile = document.createElement("canvas")
    toile.width = l; toile.height = h
    const ctx = toile.getContext("2d")
    if (!ctx) return null
    ctx.fillStyle = "#fff"
    ctx.fillRect(0, 0, l, h)
    ctx.drawImage(image, 0, 0, l, h)
    dessinerTraits(ctx, traits, l, h)
    try {
      const blob = await new Promise<Blob | null>((ok) => toile.toBlob(ok, "image/jpeg", 0.92))
      if (!blob) throw new Error("vide")
      return new File([blob], nomAnnote(nom), { type: "image/jpeg" })
    } catch {
      setErreur("Cette image ne peut pas être exportée (elle vient d'un site extérieur).")
      return null
    }
  }

  const telecharger = async () => {
    const f = await exporter()
    if (!f) return
    const url = URL.createObjectURL(f)
    const a = document.createElement("a")
    a.href = url
    a.download = f.name
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const utiliser = async () => {
    const f = await exporter()
    if (!f) return
    if (surUtiliser) { surUtiliser(f); surFermer(); return }
    const detail: DetailJoindre = { fichiers: [f] }
    window.dispatchEvent(new CustomEvent<DetailJoindre>(EVENEMENT_JOINDRE, { detail }))
    if (!detail.recu) {
      setErreur("La barre de saisie du chat n'est pas ouverte : téléchargez l'image, ou revenez au chat.")
      return
    }
    surFermer()
  }

  const bouton: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", gap: 6, height: 36, padding: "0 12px",
    borderRadius: 999, border: "1px solid rgb(255 255 255 / .25)", cursor: "pointer",
    background: "rgb(255 255 255 / .1)", color: "#fff", fontSize: 13, fontWeight: 600,
  }

  return createPortal(
    // UN PORTAIL REMONTE SES ÉVÉNEMENTS AUX PARENTS REACT, pas aux parents du DOM :
    // sans cet arrêt, chaque clic dans l'annotateur rejouait le clic de l'image
    // d'en dessous (« ouvrir en grand » dans un nouvel onglet).
    <div role="dialog" aria-modal="true" aria-label="Annoter l'image" data-testid="annotateur"
         onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}
         onKeyDown={(e) => e.stopPropagation()}
         style={{ position: "fixed", inset: 0, zIndex: 1000, background: "#0b0e11",
                  display: "flex", flexDirection: "column", height: "100dvh",
                  paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8,
                    padding: "calc(10px + env(safe-area-inset-top)) 14px 10px" }}>
        <div role="radiogroup" aria-label="Couleur du trait" style={{ display: "flex", gap: 8, marginRight: 6 }}>
          {COULEURS.map((c) => (
            <button key={c.valeur} type="button" role="radio" aria-checked={couleur === c.valeur}
                    aria-label={c.nom} title={c.nom} data-testid="annoter-couleur"
                    onClick={() => setCouleur(c.valeur)}
                    style={{ width: 30, height: 30, borderRadius: 999, cursor: "pointer", background: c.valeur,
                             border: couleur === c.valeur ? "3px solid #fff" : "2px solid rgb(255 255 255 / .35)",
                             boxShadow: couleur === c.valeur ? "0 0 0 2px rgb(0 0 0 / .5)" : "none" }} />
          ))}
        </div>
        <button type="button" onClick={annuler} disabled={!traits.length} style={{ ...bouton, opacity: traits.length ? 1 : .45 }}
                title="Annuler le dernier trait (Ctrl+Z)">
          <Undo2Icon className="size-4" /> Annuler
        </button>
        <button type="button" onClick={() => setTraits([])} disabled={!traits.length}
                style={{ ...bouton, opacity: traits.length ? 1 : .45 }} title="Effacer tous les traits">
          <Trash2Icon className="size-4" /> Tout effacer
        </button>
        <div style={{ flex: 1 }} />
        <button type="button" onClick={telecharger} disabled={!image} style={bouton} data-testid="annoter-telecharger">
          <DownloadIcon className="size-4" /> Télécharger
        </button>
        <button type="button" onClick={utiliser} disabled={!image} data-testid="annoter-utiliser"
                style={{ ...bouton, background: "var(--marque-primary, #2f6b3a)", borderColor: "transparent" }}>
          <ImagePlusIcon className="size-4" /> Utiliser dans la conversation
        </button>
        <button type="button" onClick={surFermer} aria-label="Fermer" title="Fermer (Échap)"
                style={{ ...bouton, width: 36, padding: 0, justifyContent: "center" }}>
          <XIcon className="size-4" />
        </button>
      </div>
      {erreur && (
        <div role="alert" style={{ color: "#ffb4a8", fontSize: 13, padding: "0 16px 8px" }}>{erreur}</div>
      )}
      {/* La marge vit sur l'enveloppe ; la zone MESURÉE n'en a pas — sinon l'image
          débordait de la largeur des marges au téléphone. */}
      <div style={{ flex: 1, minHeight: 0, padding: "0 12px 12px", display: "flex" }}>
      <div ref={zoneRef} style={{ flex: 1, minWidth: 0, minHeight: 0, display: "grid", placeItems: "center" }}>
        {image && taille ? (
          <canvas ref={toileRef} data-testid="annoter-toile"
                  onPointerDown={surAppui} onPointerMove={surMouvement}
                  onPointerUp={surRelache} onPointerCancel={surRelache}
                  style={{ width: taille.l, height: taille.h, touchAction: "none", cursor: "crosshair",
                           borderRadius: 8, boxShadow: "0 8px 30px rgb(0 0 0 / .45)" }} />
        ) : !erreur ? (
          <div style={{ color: "rgb(255 255 255 / .7)", fontSize: 13 }}>Ouverture de l'image…</div>
        ) : null}
      </div>
      </div>
    </div>,
    document.body,
  )
}

/** LE CRAYON posé sur une image. `src` : une adresse locale (blob: ou data:) déjà chargée. */
export function BoutonAnnoter({ src, nom, surUtiliser, taille = 32, style }: {
  src: string | null | undefined
  nom?: string
  surUtiliser?: (fichier: File) => void
  taille?: number
  style?: React.CSSProperties
}) {
  const [ouvert, setOuvert] = useState(false)
  const fermer = useCallback(() => setOuvert(false), [])
  if (!src) return null
  return (
    <>
      <button type="button" data-testid="annoter"
              title="Annoter : dessiner sur l'image" aria-label="Annoter : dessiner sur l'image"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOuvert(true) }}
              style={{
                width: taille, height: taille, display: "grid", placeItems: "center", cursor: "pointer",
                borderRadius: 999, border: "none", color: "#fff",
                // Même fond que le bouton de téléchargement : lisible sur un ciel
                // clair comme sur une haie sombre.
                background: "rgba(11,14,17,0.55)", backdropFilter: "blur(4px)",
                ...style,
              }}>
        <PencilIcon style={{ width: taille * 0.45, height: taille * 0.45 }} />
      </button>
      {ouvert && <Annotateur src={src} nom={nom} surFermer={fermer} surUtiliser={surUtiliser} />}
    </>
  )
}
