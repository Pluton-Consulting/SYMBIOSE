/**
 * Banc de RECETTE — joue le cahier des charges dans un vrai navigateur.
 *
 * Différence avec les deux bancs existants, et raison d'être de celui-ci :
 *   * `backend/scripts/bench/campagne.py` appelle le graphe DANS le conteneur.
 *     Rapide et stable, mais il ne prouve rien de la chaîne réelle : ni nginx,
 *     ni l'authentification, ni le rendu, ni le cloisonnement appliqué à un
 *     utilisateur connecté.
 *   * `e2e/interface.mjs` pilote le navigateur mais ne juge que le RENDU.
 *
 * Ici on juge le FOND, vu par l'utilisateur, à travers toute la chaîne. C'est
 * le seul niveau où « l'application répond-elle au cahier des charges » a un
 * sens vérifiable.
 *
 * MODE ATTACHÉ UNIQUEMENT. On reprend une session déjà ouverte : c'est ce qui
 * évite d'avoir à manipuler un lien magique, et ce qui garantit qu'on teste
 * exactement les droits d'un vrai compte. Rien n'est saisi ni stocké ici.
 *
 *   chrome.exe --remote-debugging-port=9222 \
 *              --user-data-dir="%LOCALAPPDATA%\Temp\chrome-bench" <url-app>
 *   BENCH_CDP=http://localhost:9222 node e2e/recette.mjs [--serie X] [--limite N]
 *
 * CE QUI EST NOTÉ. Chaque question porte des contrôles DURS, écrits à l'avance
 * et sans modèle : présence ou absence de termes, longueur plancher, jetons de
 * masquage qui ne doivent pas fuir, aveu d'ignorance attendu. Un contrôle dur
 * qui tombe est un fait, pas une opinion — c'est sur eux seuls que repose le
 * verdict. Ce qu'aucune règle ne sait voir est signalé « à lire », jamais
 * compté comme réussite.
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs"
import { chromium } from "playwright-core"

const CDP = process.env.BENCH_CDP || "http://localhost:9222"
const DELAI_REPONSE = 180_000
const PAUSE = Number(process.env.BENCH_PAUSE || 3000)

const args = process.argv.slice(2)
const opt = (nom) => { const i = args.indexOf(nom); return i >= 0 ? args[i + 1] : null }
const SERIE = opt("--serie")
const LIMITE = Number(opt("--limite") || 0)

const VERT = "\x1b[92m", ROUGE = "\x1b[91m", JAUNE = "\x1b[93m", GRIS = "\x1b[90m", RAZ = "\x1b[0m"

// ── Interaction avec le chat (sélecteurs éprouvés par interface.mjs) ──
function saisie(page) {
  return page.getByTestId("saisie-message")
    .or(page.locator('textarea[placeholder*="Posez votre question"]')).first()
}
function boutonEnvoyer(page) {
  return page.getByTestId("envoyer-message")
    .or(page.locator("button").filter({ hasText: /^Envoyer$/ })).first()
}

const SONDE = () => {
  const zone = document.querySelector('[data-testid="liste-messages"]')
    || [...document.querySelectorAll("div")].find((d) => {
      const s = getComputedStyle(d)
      return s.overflowY === "auto" && d.scrollHeight > 0
        && d.querySelector("div") && d.clientHeight > 200
    })
  if (!zone) return null
  const marques = [...zone.querySelectorAll('[data-testid="message-assistant"]')]
  const bulles = marques.length ? marques : [...zone.children].filter(
    (e) => getComputedStyle(e).alignSelf === "flex-start" && e.innerText.trim())
  return {
    nb: bulles.length,
    dernier: bulles.length ? bulles[bulles.length - 1].innerText : "",
  }
}

async function sonder(page) {
  return page.evaluate(`(${SONDE.toString()})()`)
}

/** Envoie une question et rend la réponse, une fois le flux stabilisé. */
async function demander(page, texte) {
  const avant = (await sonder(page))?.nb ?? 0
  await saisie(page).fill(texte)
  await boutonEnvoyer(page).click()

  const debut = Date.now()
  const limite = debut + DELAI_REPONSE
  let precedent = -1, stable = 0
  while (Date.now() < limite) {
    await page.waitForTimeout(700)
    const etat = await sonder(page)
    if (!etat || etat.nb <= avant) continue
    const taille = (etat.dernier || "").length
    if (taille > 0 && taille === precedent) {
      if (++stable >= 2) return { texte: etat.dernier, ms: Date.now() - debut }
    } else stable = 0
    precedent = taille
  }
  throw new Error(`aucune réponse stabilisée en ${DELAI_REPONSE / 1000} s`)
}

// ── Contrôles durs ────────────────────────────────────────────────────
const sansAccent = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()

// Un aveu d'ignorance est une BONNE réponse quand la donnée manque : le cahier
// des charges l'exige (§5 « il ne doit pas inventer d'information »).
const AVEUX = ["je n'ai pas", "je ne trouve", "aucun", "aucune", "pas d'information",
  "pas trouve", "n'ai rien", "ne dispose pas", "a completer", "[a completer]",
  "n'existe pas", "pas de donnee"]

function controler(reponse, q) {
  const brut = reponse.texte || ""
  const plat = sansAccent(brut)
  const echecs = []

  if (q.min_caracteres && brut.trim().length < q.min_caracteres)
    echecs.push(`réponse trop courte (${brut.trim().length} < ${q.min_caracteres})`)

  for (const t of q.doit_contenir || [])
    if (!plat.includes(sansAccent(t))) echecs.push(`manque « ${t} »`)

  for (const t of q.ne_doit_pas_contenir || [])
    if (plat.includes(sansAccent(t))) echecs.push(`contient « ${t} » (interdit)`)

  // Un de ces termes suffit : utile quand plusieurs formulations conviennent.
  if (q.au_moins_un && !q.au_moins_un.some((t) => plat.includes(sansAccent(t))))
    echecs.push(`aucun de : ${q.au_moins_un.join(", ")}`)

  if (q.doit_avouer && !AVEUX.some((a) => plat.includes(a)))
    echecs.push("devait admettre ne pas savoir, ne l'a pas fait")

  // Les jetons de masquage ne doivent JAMAIS atteindre l'écran : leur présence
  // signifie que la réhydratation a échoué et que l'utilisateur lit du balisage.
  const fuite = brut.match(/\[(PER|ORG|LOC|MAIL|TEL|MONTANT|IBAN|SIRET)_\d+\]/g)
  if (fuite) echecs.push(`jetons de masquage visibles : ${[...new Set(fuite)].join(" ")}`)

  if (/```(action|ui)\b/.test(brut)) echecs.push("bloc technique brut affiché")
  if (/<\/?(longcat_tool_call|tool_call|function_call)/i.test(brut))
    echecs.push("balisage d'outil visible")

  if (q.max_secondes && reponse.ms > q.max_secondes * 1000)
    echecs.push(`trop lent (${(reponse.ms / 1000).toFixed(0)} s > ${q.max_secondes} s)`)

  return echecs
}

// ── Exécution ─────────────────────────────────────────────────────────
async function ongletApplication(navigateur) {
  for (const ctx of navigateur.contexts())
    for (const page of ctx.pages()) {
      const u = page.url()
      if (u.startsWith("http") && !u.includes("/login")) return page
    }
  throw new Error("aucun onglet applicatif connecté trouvé")
}

async function main() {
  const series = JSON.parse(readFileSync(new URL("./recette.json", import.meta.url), "utf8"))
  let questions = series.questions
  if (SERIE) questions = questions.filter((q) => q.serie === SERIE)
  if (LIMITE) questions = questions.slice(0, LIMITE)
  if (!questions.length) { console.error("aucune question à jouer"); process.exit(2) }

  const navigateur = await chromium.connectOverCDP(CDP)
  const page = await ongletApplication(navigateur)
  console.log(`${GRIS}Onglet : ${page.url()}${RAZ}`)
  console.log(`${GRIS}${questions.length} question(s)${RAZ}\n`)

  const resultats = []
  let reussi = 0, rate = 0

  for (const [i, q] of questions.entries()) {
    const rang = `${String(i + 1).padStart(3)}/${questions.length}`
    process.stdout.write(`${GRIS}${rang} [${q.serie}] ${q.question.slice(0, 62)}…${RAZ}\n`)
    let reponse, echecs
    try {
      reponse = await demander(page, q.question)
      echecs = controler(reponse, q)
    } catch (e) {
      reponse = { texte: "", ms: 0 }
      echecs = [`aucune réponse : ${e.message}`]
    }
    if (echecs.length) {
      rate++
      console.log(`     ${ROUGE}ÉCHEC${RAZ} ${echecs.join(" · ")}`)
      console.log(`     ${GRIS}${(reponse.texte || "").replace(/\s+/g, " ").slice(0, 200)}${RAZ}`)
    } else {
      reussi++
      console.log(`     ${VERT}ok${RAZ} ${GRIS}${(reponse.ms / 1000).toFixed(1)} s${RAZ}`)
      if (q.a_lire)
        console.log(`     ${JAUNE}à lire${RAZ} ${GRIS}${(reponse.texte || "").replace(/\s+/g, " ").slice(0, 180)}${RAZ}`)
    }
    resultats.push({ ...q, reponse: reponse.texte, ms: reponse.ms, echecs })
    await page.waitForTimeout(PAUSE)
  }

  mkdirSync(new URL("./resultats", import.meta.url), { recursive: true })
  const chemin = new URL(`./resultats/recette-${series.version}.json`, import.meta.url)
  writeFileSync(chemin, JSON.stringify({ questions: resultats }, null, 2), "utf8")

  console.log(`\n${reussi} réussi(s) / ${rate} échec(s) sur ${questions.length}`)
  console.log(`${GRIS}Détail : ${chemin.pathname}${RAZ}`)
  await navigateur.close().catch(() => {})
  process.exit(rate ? 1 : 0)
}

main().catch((e) => { console.error(`${ROUGE}${e.stack || e.message}${RAZ}`); process.exit(2) })
