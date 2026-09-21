import { createRoot } from "react-dom/client"
import { VisuelPaysager } from "@/components/blocks/business/VisuelPaysager"
import { PiecesJointes } from "@/components/chat/PiecesJointes"
import { EVENEMENT_JOINDRE, type DetailJoindre } from "@/components/chat/Annoter"

const w = window as any
w.__ouvertures = 0
w.open = () => { w.__ouvertures += 1; return null }
w.__recus = []
window.addEventListener(EVENEMENT_JOINDRE, (e) => {
  const d = (e as CustomEvent<DetailJoindre>).detail
  d.recu = true
  w.__recus.push(...d.fichiers)
})

// Une « photo » de 800 × 600 : un fond vert uni, facile à distinguer d'un trait rouge.
const c = document.createElement("canvas"); c.width = 800; c.height = 600
const x = c.getContext("2d")!; x.fillStyle = "#2e7d32"; x.fillRect(0, 0, 800, 600)
const url = c.toDataURL("image/jpeg", 0.95)
const b64 = url.split(",")[1]

createRoot(document.getElementById("app")!).render(
  <div style={{ maxWidth: 620, width: "100%", boxSizing: "border-box", padding: 12, ["--bloc-largeur" as any]: "620px" }}>
    <div id="visuel"><VisuelPaysager titre="Essai" images={[{ url, legende: "Après (projet)" }]} /></div>
    <div id="pieces" style={{ marginTop: 20 }}><PiecesJointes pieces={[{ nom: "photo.jpg", mime: "image/jpeg", b64 }]} /></div>
  </div>
)
