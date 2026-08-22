/**
 * La marque Symbiose Paysage, en un seul endroit.
 *
 * Jumeau du `Logo.tsx` de l'autre projet, MÊME SIGNATURE : `Logo({ taille })`.
 * C'est ce contrat commun qui permet à `nav/EnTete.tsx` d'être du socle —
 * l'en-tête appelle un logo sans savoir s'il est dessiné en SVG inline, en
 * image, ou en lettres.
 *
 * Ici c'est un fichier SVG servi par `public/` : le logotype est un MOT
 * (« symbiose paysage » écrit), pas un symbole — le redessiner en JSX
 * n'apporterait rien et le figerait dans le code.
 */

/** Le logotype seul. `taille` est la hauteur du texte, comme chez le jumeau. */
export function MarqueSymbiose({ taille = 26 }: { taille?: number }) {
  return (
    <img
      src="/symbiose-paysage.svg"
      alt="Symbiose Paysage"
      style={{ height: taille * 1.15, width: "auto", display: "block", flexShrink: 0 }}
    />
  )
}

/**
 * Marque + nom. Le logotype contenant DÉJÀ le nom écrit, il n'y a rien à
 * ajouter à côté — d'où l'absence du <span> que porte le jumeau. La signature,
 * elle, reste la même : c'est tout ce que l'en-tête exige.
 */
export default function Logo({ taille = 20 }: { taille?: number }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center" }}>
      <MarqueSymbiose taille={taille * 1.3} />
    </span>
  )
}
