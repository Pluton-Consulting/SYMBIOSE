import { createRoot } from "react-dom/client"
import { VisuelPaysager } from "@/components/blocks/business/VisuelPaysager"
import InputBar from "@/components/chat/InputBar"

const w = window as any
w.__ouvertures = 0
w.open = () => { w.__ouvertures += 1; return null }
w.__envois = []
const c = document.createElement("canvas"); c.width = 800; c.height = 600
const x = c.getContext("2d")!; x.fillStyle = "#2e7d32"; x.fillRect(0, 0, 800, 600)
const url = c.toDataURL("image/jpeg", 0.95)
w.__photo = url

createRoot(document.getElementById("app")!).render(
  <div style={{ maxWidth: 700, width: "100%", padding: 12, boxSizing: "border-box", ["--bloc-largeur" as any]: "620px" }}>
    <div id="visuel"><VisuelPaysager titre="Essai" images={[{ url, legende: "Après (projet)" }]} /></div>
    <InputBar token="jeton" onSend={(t, p) => { w.__envois.push({ t, p: (p || []).map((q) => ({ name: q.name, mime: q.mime, n: q.b64.length })) }) }} />
  </div>
)
