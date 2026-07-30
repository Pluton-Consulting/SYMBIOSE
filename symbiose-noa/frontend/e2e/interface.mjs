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
 * DEUX MODES.
 *
 * 1. ATTACHÉ (recommandé) — tu ouvres l'application toi-même, tu te connectes,
 *    et le banc reprend CETTE session. Cela résout d'un coup les deux obstacles :
 *    l'accès réseau (ton navigateur sait joindre l'application) et le lien
 *    magique (tu es déjà authentifié). Rien n'est saisi ni stocké côté banc.
 *
 *      npm i --no-save playwright-core
 *      # puis, dans un profil SÉPARÉ — obligatoire depuis Chrome 136, et de
 *      # toute façon souhaitable : le banc ne voit que ce profil-là.
 *      chrome.exe --remote-debugging-port=9222 \
 *                 --user-data-dir="%LOCALAPPDATA%\Temp\chrome-bench" <url-app>
 *      BENCH_CDP=http://localhost:9222 node e2e/interface.mjs
 *
 * 2. AUTONOME — le banc lance son propre navigateur et se connecte via un lien
 *    magique fourni par l'environnement (l'application n'a pas de mot de passe).
 *    Le lien n'est jamais journalisé.
 *
 *      BENCH_URL=http://localhost:3000 \
 *      BENCH_LIEN_MAGIQUE='http://.../verify?token=...&email=...' \
 *      node e2e/interface.mjs
 *
 * Options communes :
 *     BENCH_VISIBLE=1     mode autonome : ouvre une fenêtre visible
 *     BENCH_CAPTURES=1    enregistre une capture par cas dans e2e/captures/
 *     BENCH_LECTURE=1     n'envoie AUCUN message ; vérifie seulement ce qui est
 *                         déjà affiché. Utile pour un premier contact prudent
 *                         sur une instance de production.
 */
import { mkdirSync } from "node:fs"

// playwright-core suffit et ne télécharge aucun navigateur : en mode attaché,
// c'est le navigateur DÉJÀ ouvert qui est piloté.
let chromium
try { ({ chromium } = await import("playwright-core")) }
catch { ({ chromium } = await import("playwright")) }

const CDP = process.env.BENCH_CDP
const LIEN = process.env.BENCH_LIEN_MAGIQUE
const VISIBLE = process.env.BENCH_VISIBLE === "1"
const CAPTURES = process.env.BENCH_CAPTURES === "1"
const LECTURE_SEULE = process.env.BENCH_LECTURE === "1"
const DELAI_REPONSE = 120_000
// Pas `URL` : ce nom masquerait le constructeur global du même nom, dont on se
// sert pour lire l'origine de l'onglet attaché.
let BASE = process.env.BENCH_URL || "http://localhost:3000"

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

/** Retrouve l'onglet de l'application parmi ceux déjà ouverts. */
async function ongletApplication(navigateur) {
  const pages = navigateur.contexts().flatMap((c) => c.pages())
  if (!pages.length) throw new Error("aucun onglet ouvert dans le navigateur attaché")
  // Priorité à un onglet qui montre déjà le chat, sinon le premier onglet
  // dont l'adresse n'est pas une page interne du navigateur.
  for (const p of pages) {
    if (await p.getByTestId("saisie-message").count()) return p
  }
  const utile = pages.find((p) => /^https?:/.test(p.url()))
  if (!utile) throw new Error("aucun onglet sur une page web — ouvre l'application d'abord")
  return utile
}

async function main() {
  let navigateur, contexte, page, attache = false

  if (CDP) {
    // Mode attaché : on reprend la session ouverte par l'utilisateur.
    navigateur = await chromium.connectOverCDP(CDP)
    attache = true
    page = await ongletApplication(navigateur)
    BASE = new URL(page.url()).origin
    console.log(`${GRIS}attaché à ${BASE} — onglet : ${page.url()}${RAZ}`)
  } else {
    if (!LIEN) {
      console.error("Ni BENCH_CDP ni BENCH_LIEN_MAGIQUE : aucun moyen de se connecter.")
      process.exit(2)
    }
    navigateur = await chromium.launch({ headless: !VISIBLE })
    contexte = await navigateur.newContext({ viewport: { width: 1440, height: 900 } })
    page = await contexte.newPage()
    await page.goto(LIEN, { waitUntil: "networkidle" })
  }

  try {
    if (!attache || !(await page.getByTestId("saisie-message").count())) {
      await page.goto(`${BASE}/chat`, { waitUntil: "networkidle" })
    }
    const connecte = await page.getByTestId("saisie-message").count()
    verdict("session authentifiée sur le chat", connecte > 0,
            attache ? "connecte-toi dans le navigateur, puis relance"
                    : "lien magique expiré ou déjà consommé ?")
    if (!connecte) return

    if (LECTURE_SEULE) {
      const etapes = await page.getByTestId("etape-reflexion").count()
      const bulles = await page.getByTestId("message-assistant").count()
      verdict("chemin de réflexion présent", etapes > 0, `${etapes} étape(s)`)
      console.log(`${GRIS}lecture seule : ${bulles} réponse(s) déjà affichée(s), `
                  + `aucun message envoyé.${RAZ}`)
      await capture(page, "00-lecture-seule")
      return
    }

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
    await page.goto(`${BASE}/accueil`, { waitUntil: "networkidle" })
    await page.goto(`${BASE}/chat`, { waitUntil: "networkidle" })
    await page.waitForTimeout(2500)
    const apres = await page.getByTestId("message-assistant").count()
    verdict("la conversation est retrouvée après changement d'onglet",
            apres >= avant, `${avant} message(s) avant, ${apres} après`)
    await capture(page, "04-retour-onglet")

  } finally {
    // En mode attaché, on se contente de se DÉTACHER : le navigateur appartient
    // à l'utilisateur, le banc n'a pas à le fermer sous ses yeux.
    if (attache) await navigateur.close().catch(() => {})
    else await navigateur.close()
  }

  console.log(`\n  ${ok} contrôle(s) OK, ${ko} en échec`)
  if (echecs.length) console.log(`  ${ROUGE}${echecs.join("\n  ")}${RAZ}`)
  process.exit(ko ? 1 : 0)
}

main().catch((e) => { console.error(e); process.exit(2) })
