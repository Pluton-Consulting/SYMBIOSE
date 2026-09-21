import { chromium } from "playwright-core"
const exe = process.env.CHROME || process.env.HOME + "/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
const D = process.argv[2]
const echecs = []
const ok = (nom, cond, detail = "") => { console.log(`  ${cond ? "✓" : "✗"} ${nom}${!cond && detail ? "  → " + detail : ""}`); if (!cond) echecs.push(nom) }

const nav = await chromium.launch({ executablePath: exe, headless: true })
const page = await nav.newPage({ viewport: { width: 1100, height: 800 }, acceptDownloads: true })
const erreurs = []
page.on("pageerror", (e) => erreurs.push(String(e)))
page.on("console", (m) => { if (m.type() === "error") erreurs.push(m.text()) })
await page.goto("file://" + D + "/planche.html")
await page.waitForSelector("#visuel [data-testid=annoter]")

ok("le crayon est posé sur l'image de la planche", await page.locator("#visuel [data-testid=annoter]").count() === 1)
ok("le crayon est posé sur la vignette de la pièce jointe", await page.locator("#pieces [data-testid=annoter]").count() === 1)

await page.click("#visuel [data-testid=annoter]")
await page.waitForSelector("[data-testid=annoter-toile]")
ok("le clic sur le crayon n'ouvre PAS l'image dans un onglet", await page.evaluate(() => window.__ouvertures) === 0)
ok("cinq couleurs en haut", await page.locator("[data-testid=annoter-couleur]").count() === 5)
const boite = await page.locator("[data-testid=annoter-toile]").boundingBox()
ok("l'image s'ouvre en grand (plus large que la planche)", boite && boite.width > 700, JSON.stringify(boite))

// Un trait ROUGE horizontal au milieu de l'image.
await page.locator("[data-testid=annoter-couleur]").nth(0).click()
const y = boite.y + boite.height / 2
await page.mouse.move(boite.x + boite.width * 0.2, y)
await page.mouse.down()
for (let i = 1; i <= 20; i++) await page.mouse.move(boite.x + boite.width * (0.2 + 0.03 * i), y)
await page.mouse.up()
// Un second trait, jaune, puis « Annuler » le retire.
await page.locator("[data-testid=annoter-couleur]").nth(1).click()
await page.mouse.move(boite.x + boite.width * 0.5, boite.y + boite.height * 0.2)
await page.mouse.down(); await page.mouse.move(boite.x + boite.width * 0.5, boite.y + boite.height * 0.8); await page.mouse.up()
await page.getByRole("button", { name: /Annuler/ }).click()
ok("dessiner n'a ouvert aucun onglet (le portail ne rejoue pas le clic du parent)", await page.evaluate(() => window.__ouvertures) === 0)

// Télécharger.
const [dl] = await Promise.all([page.waitForEvent("download"), page.click("[data-testid=annoter-telecharger]")])
ok("téléchargement : un JPEG nommé d'après l'image", /apres-projet-annotee\.jpg$/.test(dl.suggestedFilename()), dl.suggestedFilename())

// Réutiliser dans la conversation.
await page.click("[data-testid=annoter-utiliser]")
await page.waitForFunction(() => window.__recus.length > 0, null, { timeout: 5000 }).catch(() => {})
const info = await page.evaluate(async () => {
  const f = window.__recus[0]
  if (!f) return null
  const bmp = await createImageBitmap(f)
  const c = document.createElement("canvas"); c.width = bmp.width; c.height = bmp.height
  const x = c.getContext("2d"); x.drawImage(bmp, 0, 0)
  const px = (a, b) => Array.from(x.getImageData(Math.round(a * bmp.width), Math.round(b * bmp.height), 1, 1).data)
  return { nom: f.name, type: f.type, l: bmp.width, h: bmp.height,
           trait: px(0.5, 0.5), fond: px(0.5, 0.15), jaune: px(0.5, 0.3) }
})
ok("l'image annotée arrive dans la barre de saisie (événement reçu)", !!info)
ok("… en JPEG, à la résolution de l'image (800 × 600)", info && info.type === "image/jpeg" && info.l === 800 && info.h === 600, JSON.stringify(info))
ok("… le trait rouge est bien dessiné au milieu", info && info.trait[0] > 180 && info.trait[1] < 90, JSON.stringify(info?.trait))
ok("… le fond reste la photo (vert)", info && info.fond[1] > 90 && info.fond[0] < 90, JSON.stringify(info?.fond))
ok("… le trait jaune annulé n'y est plus", info && !(info.jaune[0] > 180 && info.jaune[1] > 180), JSON.stringify(info?.jaune))
ok("l'annotateur se ferme après « Utiliser »", await page.locator("[data-testid=annotateur]").count() === 0)

// La vignette de la bulle, et Échap pour fermer.
await page.click("#pieces [data-testid=annoter]")
await page.waitForSelector("[data-testid=annoter-toile]")
ok("la vignette s'annote aussi, sans ouvrir d'onglet", await page.evaluate(() => window.__ouvertures) === 0)
await page.keyboard.press("Escape")
ok("Échap ferme l'annotateur", await page.locator("[data-testid=annotateur]").count() === 0)

// Au téléphone : l'image tient dans l'écran et le tactile dessine.
const tel = await nav.newPage({ viewport: { width: 390, height: 780 }, hasTouch: true, isMobile: true })
await tel.goto("file://" + D + "/planche.html")
await tel.waitForSelector("#visuel [data-testid=annoter]")
await tel.tap("#visuel [data-testid=annoter]")
await tel.waitForSelector("[data-testid=annoter-toile]")
const b2 = await tel.locator("[data-testid=annoter-toile]").boundingBox()
ok("téléphone : l'image tient dans la largeur de l'écran, marges comprises", b2 && b2.x >= 11 && b2.x + b2.width <= 379 && b2.width > 300, JSON.stringify(b2))
const large = await tel.evaluate(() => document.documentElement.scrollWidth)
ok("téléphone : aucun défilement horizontal", large <= 390, String(large))

await page.click("#visuel [data-testid=annoter]")
await page.waitForSelector("[data-testid=annoter-toile]")
await page.mouse.move(boite.x + 100, boite.y + 100); await page.mouse.down(); await page.mouse.move(boite.x + 400, boite.y + 300, { steps: 10 }); await page.mouse.up()


ok("aucune erreur JavaScript", erreurs.length === 0, erreurs.join(" | "))
await nav.close()
console.log(echecs.length ? `\n✗ ${echecs.length} échec(s)` : "\n✓ 0 échec")
process.exit(echecs.length ? 1 : 0)
