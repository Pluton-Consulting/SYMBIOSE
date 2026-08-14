"use client"

/**
 * LE PONT ENTRE UN DOCUMENT DE L'ENTREPRISE ET UNE VISIONNEUSE EXTEND UI.
 *
 * Les visionneuses ne savent PAS aller chercher un fichier protégé : elles
 * font un `fetch(url)` nu, sans en-tête. Or tous les documents d'ici sont
 * derrière un jeton. Ce composant fait donc le trajet lui-même — récupération
 * authentifiée, puis URL d'objet locale — et règle au passage les quatre
 * pièges relevés à la lecture du code des visionneuses :
 *
 *   1. AUCUNE n'accepte un Blob. Trois veulent une URL (docx, xlsx, pdf), la
 *      quatrième veut le TEXTE brut (csv).
 *   2. Le DOCX exige un nom finissant par « .docx ». Et l'échec est SILENCIEUX :
 *      le composant guette un message d'erreur qui ne correspond plus à celui
 *      de la version installée de la bibliothèque. Un nom sans extension
 *      donnerait un cadre vide, sans explication. On corrige le nom ici — c'est
 *      exactement la panne qu'on a déjà vue côté serveur avec « test 2 ».
 *   3. Aucune ne révoque l'URL d'objet qu'on lui passe : sans ménage, chaque
 *      aperçu fuit sa mémoire.
 *   4. `isDark` / `onIsDarkChange` sont OBLIGATOIRES sur docx et xlsx, sans
 *      valeur par défaut.
 *
 * Les visionneuses portent leurs propres classes Tailwind, donc les couleurs
 * de la charte via `theme.css` : rien à repeindre ici.
 */

import * as React from "react"
import { DocxViewerPreview } from "@/components/extend/docx-viewer"
import { XlsxViewerPreview } from "@/components/extend/xlsx-viewer"
import { CsvViewer } from "@/components/extend/csv-viewer"
import { PDFViewer } from "@/components/extend/pdf-viewer"

/** Formats que l'on sait afficher, et rien d'autre. */
export type FormatApercu = "docx" | "xlsx" | "csv" | "pdf"

const EXTENSIONS: Record<FormatApercu, string> = {
  docx: ".docx",
  xlsx: ".xlsx",
  csv: ".csv",
  pdf: ".pdf",
}

/** Le nom que la bibliothèque doit voir : elle valide l'extension, pas le type
 *  MIME. Un « test 2 » sans extension casse le lecteur DOCX en silence. */
function nomValide(nom: string | undefined, format: FormatApercu): string {
  const base = (nom || "document").trim() || "document"
  const attendue = EXTENSIONS[format]
  return base.toLowerCase().endsWith(attendue) ? base : `${base}${attendue}`
}

export function formatDepuisNom(nom: string | undefined): FormatApercu | null {
  const n = (nom || "").toLowerCase()
  if (n.endsWith(".docx") || n.endsWith(".doc")) return "docx"
  if (n.endsWith(".xlsx") || n.endsWith(".xls")) return "xlsx"
  if (n.endsWith(".csv") || n.endsWith(".tsv")) return "csv"
  if (n.endsWith(".pdf")) return "pdf"
  return null
}

type Props = {
  /** Chemin de l'API, ex. « /api/documents/<jeton> ». */
  url: string
  format: FormatApercu
  nom?: string
  apiUrl?: string
  backendToken?: string
  /** Hauteur de la zone. Les visionneuses posent 640px en dur ; on surcharge. */
  hauteur?: number
}

export function ApercuDocument({
  url,
  format,
  nom,
  apiUrl,
  backendToken,
  hauteur = 460,
}: Props) {
  const [objectUrl, setObjectUrl] = React.useState<string>()
  const [texte, setTexte] = React.useState<string>()
  const [erreur, setErreur] = React.useState<string>()
  const [sombre, setSombre] = React.useState(false)

  React.useEffect(() => {
    let vivant = true
    let cree: string | undefined

    const recuperer = async () => {
      setErreur(undefined)
      try {
        const base = apiUrl || ""
        const reponse = await fetch(url.startsWith("http") ? url : `${base}${url}`, {
          headers: backendToken ? { Authorization: `Bearer ${backendToken}` } : {},
        })
        if (!reponse.ok) throw new Error(`réponse ${reponse.status}`)
        const blob = await reponse.blob()
        if (!vivant) return

        if (format === "csv") {
          // Le CSV veut du TEXTE, pas une URL. `blob.text()` décode en UTF-8 ;
          // un export Excel français est souvent en windows-1252, et les
          // accents sortiraient en charabia. On détecte le cas plutôt que de
          // livrer un tableau illisible.
          const octets = await blob.arrayBuffer()
          if (!vivant) return
          const utf8 = new TextDecoder("utf-8", { fatal: false }).decode(octets)
          const suspect = utf8.includes("�")
          setTexte(suspect
            ? new TextDecoder("windows-1252").decode(octets)
            : utf8)
          return
        }

        cree = URL.createObjectURL(blob)
        setObjectUrl(cree)
      } catch (e) {
        if (vivant) {
          setErreur(e instanceof Error ? e.message : "document illisible")
        }
      }
    }

    recuperer()
    return () => {
      vivant = false
      // AUCUNE visionneuse ne libère l'URL qu'on lui a passée : sans ce
      // ménage, chaque aperçu affiché garde son fichier en mémoire.
      if (cree) URL.revokeObjectURL(cree)
    }
  }, [url, format, apiUrl, backendToken])

  if (erreur) {
    return (
      <div
        className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground"
        role="status"
      >
        Aperçu indisponible ({erreur}). Le fichier reste téléchargeable.
      </div>
    )
  }

  const enAttente = format === "csv" ? texte === undefined : objectUrl === undefined
  if (enAttente) {
    return (
      <div
        className="sym-skeleton"
        style={{ height: hauteur, width: "100%" }}
        aria-label="Chargement de l'aperçu"
      />
    )
  }

  const nomFichier = nomValide(nom, format)
  const cadre = "overflow-hidden rounded-lg border border-border bg-card"

  if (format === "csv") {
    return (
      <div className={cadre} style={{ height: hauteur }}>
        <CsvViewer data={texte} search className="h-full w-full" />
      </div>
    )
  }

  if (format === "xlsx") {
    return (
      <div className={cadre} style={{ height: hauteur }}>
        <XlsxViewerPreview
          src={objectUrl}
          fileName={nomFichier}
          isDark={sombre}
          onIsDarkChange={setSombre}
          className="h-full w-full"
        />
      </div>
    )
  }

  if (format === "pdf") {
    return (
      <div className={cadre} style={{ height: hauteur }}>
        <PDFViewer src={objectUrl} fileName={nomFichier} className="h-full w-full" />
      </div>
    )
  }

  return (
    <div className={cadre} style={{ height: hauteur }}>
      <DocxViewerPreview
        src={objectUrl}
        fileName={nomFichier}
        isDark={sombre}
        onIsDarkChange={setSombre}
        className="h-full w-full"
      />
    </div>
  )
}
