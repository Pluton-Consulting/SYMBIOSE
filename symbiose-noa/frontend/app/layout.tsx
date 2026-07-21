import type { Metadata } from "next"
import { SessionProvider } from "next-auth/react"

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
        <style dangerouslySetInnerHTML={{ __html: `
          :root {
            /* Charte graphique Symbiose — vert forêt */
            --color-primary:        #182B16;
            --color-primary-hover:  #2D5A27;
            --color-primary-mid:    #3F7A36;
            --color-primary-light:  #C8E6C0;
            --color-primary-subtle: #EDF4EC;
            --color-leaf:           #3F7A36;
            --color-canvas:         #F5F6F5;
            --color-surface:        #FFFFFF;
            --color-border:         #E8EBE8;
            --color-text-primary:   #111A10;
            --color-text-body:      #3D4D3C;
            --color-text-muted:     #8FA08E;
            --color-text-on-dark:   #FFFFFF;
            --color-on-dark-accent: #A8D4A0;
            --color-paid-bg:        #E6F4E3;
            --color-paid-text:      #2D6B26;
            --color-pending-bg:     #FDF3E3;
            --color-pending-text:   #9A6520;
            --color-progress-bg:    #E8F0FE;
            --color-progress-text:  #3557A0;
            --color-error-bg:       #FEE2E2;
            --color-error-text:     #DC2626;
            --radius-card:          20px;
            --radius-card-sm:       14px;
            --radius-pill:          9999px;
            --radius-icon:          10px;
            --shadow-card:          0 2px 12px rgba(24,43,22,0.06);
            --shadow-hover:         0 4px 20px rgba(24,43,22,0.10);
            --shadow-card-hover:    0 4px 20px rgba(24,43,22,0.10);
            --font:                 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            --font-family:          'Plus Jakarta Sans', 'Inter', sans-serif;
          }
          *, *::before, *::after { box-sizing: border-box; }
          body {
            margin: 0;
            font-family: var(--font);
            color: var(--color-text-body);
            background: var(--color-canvas);
            -webkit-font-smoothing: antialiased;
          }
          a { color: inherit; text-decoration: none; }
          button, input, select, textarea { font-family: var(--font); }
          ::-webkit-scrollbar { width: 6px; height: 6px; }
          ::-webkit-scrollbar-track { background: transparent; }
          ::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 3px; }
        ` }} />
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
