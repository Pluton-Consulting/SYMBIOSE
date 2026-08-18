// Hiérarchie : super_admin > direction > métier
// super_admin = développeur, accès total
// direction   = dirigeants, vue client + gestion app

export type Role =
  | "super_admin"
  | "direction"
  | "commercial"
  | "bureau_etudes"
  | "conducteur"
  | "administratif"
  | "terrain"

export const ROLE_LABELS: Record<string, string> = {
  super_admin:   "Super Admin",
  direction:     "Direction",
  commercial:    "Commercial",
  bureau_etudes: "Bureau d'études",
  conducteur:    "Conducteur",
  administratif: "Administratif",
  terrain:       "Terrain",
}

export const ROLE_COLORS: Record<string, string> = {
  super_admin:   "#0F1F0E",
  direction:     "#304D32",
  commercial:    "#2563eb",
  bureau_etudes: "#0891b2",
  conducteur:    "#d97706",
  administratif: "#6b7280",
  terrain:       "#92400e",
}

export interface TabDef {
  key: string
  label: string
  href: string
  roles: string[]
  /** RÉSERVÉ À QUI DÉVELOPPE. L'onglet se dessine dans la couleur à part
   *  (`--marque-dev`) : de la mécanique, pas du travail de l'entreprise. */
  dev?: boolean
}

const ALL_ROLES: string[] = [
  "super_admin",
  "direction",
  "commercial",
  "bureau_etudes",
  "conducteur",
  "administratif",
  "terrain",
]

const MANAGERS: string[] = ["super_admin", "direction"]

// LES ONGLETS DISENT CE QU'ON Y FAIT, PAS CE QU'IL Y A DEDANS.
//
// Les intitulés d'origine nommaient l'architecture : « Auto-Évolution »,
// « Skills », « Navigateur », « Commercial / Admin ». Aucun ne dit à une
// assistante ou à un conducteur de travaux ce qu'il trouvera derrière, et deux
// d'entre eux ne sont même pas du français. Un menu se lit en une seconde,
// sans mode d'emploi : il doit être écrit dans les mots du métier.
//
// Les CLÉS et les ADRESSES ne bougent pas — ce sont elles que le contrôle
// d'accès et les liens existants utilisent. Seul change ce qui est lu.
export const TABS: TabDef[] = [
  { key: "accueil",     label: "Accueil",         href: "/accueil",     roles: ALL_ROLES },
  // « Commercial / Admin » décrivait deux services ; le nom dit maintenant le
  // travail qu'on y suit, et il parle aussi bien au commercial qu'à l'atelier.
  { key: "commercial",  label: "Devis & clients", href: "/commercial",  roles: ALL_ROLES },
  {
    key: "conception",
    // « Visuels » restait vague. On y dépose un plan ou une photo, on en
    // ressort une lecture et un pré-chiffrage.
    label: "Plans & visuels",
    href: "/conception",
    roles: ["super_admin", "direction", "bureau_etudes", "conducteur"],
  },
  {
    key: "auto-evolution",
    // « Auto-Évolution » ne veut rien dire hors du code. Ce qui s'y passe :
    // l'assistant retient ce qu'on lui a appris, après relecture d'un humain.
    label: "Apprentissage",
    href: "/auto-evolution",
    roles: ["super_admin", "direction"],
  },
  {
    key: "skills",
    // « Skills » n'est pas français, et « compétences » évoque les personnes.
    // Un savoir-faire, c'est ce que la maison sait faire — et c'est bien de
    // cela qu'il s'agit.
    label: "Savoir-faire",
    href: "/skills",
    roles: MANAGERS,
  },
  {
    key: "gestion",
    // « Gestion » pouvait désigner la gestion des chantiers. Ici on regarde
    // comment l'assistant est utilisé et ce qu'il coûte.
    label: "Pilotage",
    href: "/gestion",
    roles: ["super_admin", "direction"],
  },
  // L'ONGLET « RECHERCHE WEB » A ÉTÉ RETIRÉ DU MENU, ET C'EST UN GAIN.
  //
  // Il portait une capacité que le chat n'avait pas : pour faire lire une page
  // à l'assistant, il fallait quitter la conversation, remplir un formulaire
  // dans un autre écran, puis revenir avec le résultat. Deux endroits pour une
  // seule idée — et, côté modèle, une capacité qu'il ignorait posséder : il
  // répondait « je ne peux pas accéder à internet », ce qui était vrai depuis
  // sa place.
  //
  // La navigation est désormais un GESTE du chat (`chercher_web`,
  // `ouvrir_page`) : on la demande là où le besoin naît.
  //
  // LA PAGE EXISTE TOUJOURS, à /navigateur, et reste accessible par son
  // adresse : elle porte la navigation AUTONOME — celle qui se connecte et
  // remplit des formulaires. Celle-là appelle un accord humain et un choix de
  // domaines ; elle n'a pas sa place dans un menu de tous les jours.
  {
    key: "parametres",
    label: "Paramètres",
    href: "/parametres",
    roles: MANAGERS,
  },
  // Console développeur — journaux bruts en direct, super_admin uniquement.
  // Marquée `dev` : elle se dessine dans la couleur à part, pour qu'on ne la
  // confonde jamais avec un écran de travail.
  {
    key: "superviseur",
    label: "Développeur",
    href: "/superviseur",
    roles: ["super_admin"],
    dev: true,
  },
]

export function getVisibleTabs(role: string): TabDef[] {
  return TABS.filter((t) => t.roles.includes(role))
}

export function canAccess(role: string, tabKey: string): boolean {
  const tab = TABS.find((t) => t.key === tabKey)
  return tab ? tab.roles.includes(role) : false
}
