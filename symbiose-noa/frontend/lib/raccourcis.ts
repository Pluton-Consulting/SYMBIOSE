// LES PROCESS FRÉQUENTS du menu de la barre de saisie (bouton éclair).
//
// Fichier PAR CLIENT, déclaré dans la dérive : le MÉCANISME (menu, préremplissage)
// est du socle (`InputBar.tsx`, identique des deux côtés), le CONTENU est du
// métier — les rendus d'image n'existent que chez le client qui a l'offre
// visuelle. Un clic PRÉREMPLIT la saisie, il n'envoie rien : on relit, on
// ajuste, on envoie soi-même. 31/08 : les entrées clients et CA ont été
// retirées à la demande de Noa.
export const RACCOURCIS: { libelle: string; prompt: string }[] = [
  { libelle: "Synthèse des mails (7 jours)",
    prompt: "Fais le point sur tous mes mails des 7 derniers jours : une synthèse message par message, et propose une réponse pour chacun de ceux qui en appellent une." },
  { libelle: "Dossiers en attente",
    prompt: "Quels dossiers sont en attente d’une réponse ou d’une relance, du plus ancien au plus récent ?" },
  // Les rendus d'image — l'offre visuelle de Symbiose. Le premier attend une
  // photo jointe (le trombone est à côté), le second part d'une description.
  { libelle: "Simulation avant/après sur photo",
    prompt: "Je joins une photo du jardin : fais une simulation avant/après en ajoutant [décrivez : terrasse bois, pergola, massifs…]. Garde la maison et tout le reste à l’identique." },
  { libelle: "Créer un visuel d'aménagement",
    prompt: "Prépare un visuel d’aménagement paysager : [décrivez la scène — terrain, ambiance, végétation, matériaux, saison]." },
]
