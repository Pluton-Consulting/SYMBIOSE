/**
 * Banc d'interface — pilote un vrai navigateur sur le chat.
 *
 * Il ne teste QUE ce que l'API ne peut pas prouver : le rendu. La pertinence
 * des réponses, le RAG et les actions se testent bien mieux par
 * `backend/scripts/bench/campagne.py` — dix fois plus vite et sans instabilité.
 * Ici on vérifie qu'un composant s'affiche vraiment au lieu d'un bloc de texte
 * brut, que le markdown devient des éléments, que la vue suit les messages, et
 * que le chemin de réflexion progresse.
 *
 * Prérequis (non ajouté aux dépendances du projet, c'est un outil de test) :
 *     npm i -D playwright && npx playwright install chromium
 *
 * L'authentification se fait par LIEN MAGIQUE : il n'y a pas de mot de passe
 * dans cette application. On passe donc le lien complet par l'environnement,
 * et il n'est jamais journalisé.
 *
 *     BENCH_URL=http://localhost:3000 \
 *     BENCH_LIEN_MAGIQUE='http://localhost:3000/verify?token=...&email=...' \
 *     node e2e/interface.mjs
 *
 * Options d'environnement :
 *     BENCH_VISIBLE=1     ouvre une fenêtre au lieu de tourner sans affichage
 *     BENCH_CAPTURES=1    enregistre une capture par cas dans e2e/captures/
 */
import { chromium } from "playwright"
import { mkdirSync } from "node:fs"

const URL = process.env.BENCH_URL || "http://localhost:3000"
const LIEN = process.env.BENCH_LIEN_MAGIQUE
const VISIBLE = process.env.BENCH_VISIBLE === "1"
const CAPTURES = process.env.BENCH_CAPTURES === "1"
const DELAI_REPONSE = 120_000

const VERT = "\x1b[92m", ROUGE = "\x1b[91m", GRIS = "\x1b[90m", RAZ = "\x1b[0m"
let ok = 0, ko = 0
const echecs = []

function verdict(libelle, condition, detail = "") {
  if (condition) { ok++; console.log(`  ${VERT}OK${RAZ}   ${libelle}`) }
  else {
    ko++; echecs.push(libelle)
    console.log(`  ${ROUGE}KO${RAZ}   ${libelle}`)
    if (detail) console.log(`       ${GRIS}${String(detail).slice(0, 300)}${RAZ}`)
  }
}

/** Envoie un message et attend qu'une réponse d'assistant NOUVELLE apparaisse. */
async function demander(page, texte) {
  const avant = await page.getByTestId("message-assistant").count()
  await page.getByTestId("saisie-message").fill(texte)
  await page.getByTestId("envoyer-message").click()
  await page.waitForFunction(
    (n) => document.querySelectorAll('[data-testid="message-assistant"]').length > n,
    avant, { timeout: DELAI_REPONSE })
  // La réponse arrive en flux : on attend que le texte cesse de grandir.
  const bulle = page.getByTestId("message-assistant").last()
  let precedent = -1
  for (let i = 0; i < 60; i++) {
    const actuel = (await bulle.innerText()).length
    if (actuel > 0 && actuel === precedent) break
    precedent = actuel
    await page.waitForTimeout(500)
  }
  return bulle
}

async function capture(page, nom) {
  if (!CAPTURES) return
  mkdirSync("e2e/captures", { recursive: true })
  await page.screenshot({ path: `e2e/captures/${nom}.png`, fullPage: false })
}

async function main() {
  if (!LIEN) {
    console.error("BENCH_LIEN_MAGIQUE manquant : impossible de se connecter.")
    process.exit(2)
  }

  const navigateur = await chromium.launch({ headless: !VISIBLE })
  const contexte = await navigateur.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await contexte.newPage()

  try {
    // ── Connexion ────────────────────────────────────────────────────
    await page.goto(LIEN, { waitUntil: "networkidle" })
    await page.goto(`${URL}/chat`, { waitUntil: "networkidle" })
    const connecte = await page.getByTestId("saisie-message").count()
    verdict("connexion par lien magique", connecte > 0,
            "la zone de saisie n'apparaît pas — lien expiré ou déjà consommé ?")
    if (!connecte) return

    // ── 1. Conversation courante : pas de hors-sujet ─────────────────
    let bulle = await demander(page, "saluut")
    let texte = await bulle.innerText()
    verdict("salutation : réponse non vide", texte.trim().length > 0)
    verdict("salutation : pas de note technique",
            !texte.includes("Limite d'actions"), texte.slice(0, 200))
    verdict("salutation : ne parle pas des documents",
            !/aucun document|m[ée]moire d'entreprise/i.test(texte), texte.slice(0, 200))
    await capture(page, "01-salutation")

    // ── 2. Le chemin de réflexion progresse ──────────────────────────
    const etapes = await page.getByTestId("etape-reflexion").count()
    verdict("chemin de réflexion affiché", etapes > 0, `${etapes} étape(s)`)

    // ── 3. Un composant s'affiche VRAIMENT ───────────────────────────
    bulle = await demander(page,
      "Mets dans un tableau : Terrassement 1200 m2 a 18 EUR, Plantation 340 unites a 25 EUR.")
    texte = await bulle.innerText()
    const balisesBrutes = /```ui/.test(texte)
    verdict("aucun bloc ```ui laissé en texte brut", !balisesBrutes, texte.slice(0, 200))
    const tableaux = await bulle.locator("table").count()
    const grilles = await bulle.locator('[class*="table"], [class*="Table"]').count()
    verdict("le tableau est rendu comme un composant", tableaux + grilles > 0,
            `table=${tableaux} grille=${grilles} | ${texte.slice(0, 200)}`)
    verdict("les chiffres traversent intacts",
            texte.includes("1200") || texte.includes("1 200"), texte.slice(0, 200))
    await capture(page, "02-composant")

    // ── 4. Le markdown devient des éléments, pas des astérisques ─────
    bulle = await demander(page,
      "Explique en trois points structures comment preparer une reception de chantier.")
    texte = await bulle.innerText()
    const gras = await bulle.locator("strong, b").count()
    const listes = await bulle.locator("li").count()
    verdict("markdown rendu (gras ou liste)", gras + listes > 0,
            `gras=${gras} listes=${listes}`)
    verdict("pas d'astérisques visibles", !/\*\*/.test(texte), texte.slice(0, 200))
    verdict("pas de tiret cadratin", !/[—–]/.test(texte), texte.slice(0, 200))
    await capture(page, "03-markdown")

    // ── 5. La vue suit les messages ──────────────────────────────────
    const enBas = await page.getByTestId("liste-messages").evaluate(
      (el) => el.scrollHeight - el.scrollTop - el.clientHeight < 150)
    verdict("défilement automatique jusqu'au dernier message", enBas,
            "la liste n'est pas au bas après une réponse")

    // ── 6. La conversation survit à un changement d'onglet ───────────
    const avant = await page.getByTestId("message-assistant").count()
    await page.goto(`${URL}/accueil`, { waitUntil: "networkidle" })
    await page.goto(`${URL}/chat`, { waitUntil: "networkidle" })
    await page.waitForTimeout(2500)
    const apres = await page.getByTestId("message-assistant").count()
    verdict("la conversation est retrouvée après changement d'onglet",
            apres >= avant, `${avant} message(s) avant, ${apres} après`)
    await capture(page, "04-retour-onglet")

  } finally {
    await navigateur.close()
  }

  console.log(`\n  ${ok} contrôle(s) OK, ${ko} en échec`)
  if (echecs.length) console.log(`  ${ROUGE}${echecs.join("\n  ")}${RAZ}`)
  process.exit(ko ? 1 : 0)
}

main().catch((e) => { console.error(e); process.exit(2) })
