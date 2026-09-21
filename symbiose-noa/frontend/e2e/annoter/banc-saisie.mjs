import { chromium } from "playwright-core"
const exe = process.env.CHROME || process.env.HOME + "/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
const D = process.argv[2]
const echecs = []
const ok = (nom, cond, detail = "") => { console.log(`  ${cond ? "✓" : "✗"} ${nom}${!cond && detail ? "  → " + detail : ""}`); if (!cond) echecs.push(nom) }
const nav = await chromium.launch({ executablePath: exe, headless: true })
const page = await nav.newPage({ viewport: { width: 1100, height: 900 } })
const erreurs = []
page.on("pageerror", (e) => erreurs.push(String(e)))
await page.goto("file://" + D + "/saisie.html")
await page.waitForSelector("#visuel [data-testid=annoter]")

const tracer = async () => {
  const b = await page.locator("[data-testid=annoter-toile]").boundingBox()
  await page.mouse.move(b.x + b.width * 0.2, b.y + b.height / 2); await page.mouse.down()
  await page.mouse.move(b.x + b.width * 0.8, b.y + b.height / 2, { steps: 12 }); await page.mouse.up()
}
// 1. Annoter l'image du fil, l'utiliser : elle arrive dans la barre de saisie.
await page.click("#visuel [data-testid=annoter]")
await page.waitForSelector("[data-testid=annoter-toile]")
await tracer()
await page.click("[data-testid=annoter-utiliser]")
await page.waitForSelector("[data-testid=piece-jointe]", { timeout: 5000 }).catch(() => {})
ok("l'image annotée apparaît dans la barre de saisie", await page.locator("[data-testid=piece-jointe]").count() === 1)
ok("… avec sa vignette", await page.locator("[data-testid=piece-jointe-vignette]").count() === 1)
ok("… nommée « apres-projet-annotee.jpg »", (await page.locator("[data-testid=piece-jointe]").innerText()).includes("apres-projet-annotee.jpg"))
ok("le curseur attend la demande dans le champ", await page.evaluate(() => document.activeElement?.getAttribute("data-testid")) === "saisie-message")

// 2. Annoter la pièce EN ATTENTE : sa version dessinée la remplace, pas de doublon.
await page.click("[data-testid=piece-jointe] [data-testid=annoter]")
await page.waitForSelector("[data-testid=annoter-toile]")
await tracer()
await page.click("[data-testid=annoter-utiliser]")
await page.waitForTimeout(300)
ok("annoter la pièce en attente la REMPLACE (toujours une seule pièce)", await page.locator("[data-testid=piece-jointe]").count() === 1)

// 3. Le message part avec l'image.
await page.fill("[data-testid=saisie-message]", "Place le muret sur le trait rouge")
await page.keyboard.press("Enter")
await page.waitForFunction(() => window.__envois.length > 0, null, { timeout: 5000 }).catch(() => {})
const envoi = await page.evaluate(() => window.__envois[0])
ok("le message part avec son texte", envoi?.t === "Place le muret sur le trait rouge", JSON.stringify(envoi))
ok("… et l'image annotée en pièce jointe (JPEG, contenu non vide)",
   envoi?.p?.length === 1 && envoi.p[0].mime === "image/jpeg" && envoi.p[0].n > 1000, JSON.stringify(envoi?.p))
ok("aucun onglet ouvert par erreur", await page.evaluate(() => window.__ouvertures) === 0)
ok("aucune erreur JavaScript", erreurs.length === 0, erreurs.join(" | "))
await nav.close()
console.log(echecs.length ? `\n✗ ${echecs.length} échec(s)` : "\n✓ 0 échec")
process.exit(echecs.length ? 1 : 0)
