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
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        <style dangerouslySetInnerHTML={{ __html: `
          :root {
            --color-primary:        #304D32;
            --color-primary-hover:  #26402A;
            --color-primary-mid:    #6F9040;
            --color-primary-light:  #CBD9A5;
            --color-primary-subtle: #EEF3E3;
            --color-leaf:           #9DB04F;
            --color-canvas:         #F3F5EE;
            --color-surface:        #FFFFFF;
            --color-border:         #E4E9DC;
            --color-text-primary:   #1B291A;
            --color-text-body:      #3A4A34;
            --color-text-muted:     #8A9C82;
            --color-paid-bg:        #E9F2DD;
            --color-paid-text:      #3A6B2E;
            --color-pending-bg:     #FDF3E3;
            --color-pending-text:   #9A6520;
            --color-progress-bg:    #E8F0FE;
            --color-progress-text:  #3557A0;
            --color-error-bg:       #FEE2E2;
            --color-error-text:     #DC2626;
            --radius-card:          20px;
            --radius-card-sm:       14px;
            --radius-pill:          9999px;
            --shadow-card:          0 2px 12px rgba(24,43,22,0.06);
            --shadow-hover:         0 4px 20px rgba(24,43,22,0.10);
            --font:                 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
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
