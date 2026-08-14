import type { Metadata } from "next"
import { SessionProvider } from "next-auth/react"

// LE STYLE VIT DANS DES FICHIERS CSS, PLUS DANS CE COMPOSANT.
//
// Il était injecté ici par `dangerouslySetInnerHTML` : praticable tant que
// tout tenait en styles inline, intenable dès lors que Tailwind, shadcn,
// AI Elements et Extend UI doivent lire les mêmes tokens. La chaîne est
// désormais explicite et à un seul sens :
//
//     charte.css  (les couleurs du client — LE SEUL fichier à changer)
//        ↓
//     theme.css   (la traduction vers Tailwind + shadcn — identique partout)
//        ↓
//     les composants
import "./theme.css"

export const metadata: Metadata = {
  title: "Symbiose Paysage",
  description: "Assistant IA interne Symbiose Paysage",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {/* refetch coupé : évite le repolling en boucle de /api/auth/session (jusqu'à 6 s
            quand le process compile) qui bloquait la navigation. La session reste valide via le JWT. */}
        <SessionProvider refetchOnWindowFocus={false} refetchInterval={0}>
          {children}
        </SessionProvider>
      </body>
    </html>
  )
}
