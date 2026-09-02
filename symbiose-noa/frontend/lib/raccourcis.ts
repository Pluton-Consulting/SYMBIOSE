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
  // Le rendu d'image — l'offre visuelle de Symbiose. UNE seule entrée (01/09,
  // demande de Noa : deux boutons pour la même chose embrouillaient) : avec une
  // photo jointe c'est la simulation avant/après, sans photo c'est la création.
  { libelle: "Simulation / visuel d'aménagement",
    prompt: "Je joins une photo (sinon, pars de ma description) : fais une simulation avant/après en ajoutant [décrivez : terrasse bois, pergola, massifs…]. Garde la maison et tout le reste à l’identique." },
  // LE CHIFFRAGE D'UN PLAN, EN PASSES SÉPARÉES (02/09, demande de Noa).
  //
  // Inspiré d'un workflow de métré multi-passes qui tourne en production chez
  // un autre client : six appels au modèle, un par sujet, chacun recevant le
  // résultat des précédents. Ce qui fait sa qualité tient en quatre principes,
  // et ils se transposent tels quels à une demande unique :
  //
  //  · UNE MISSION PAR PASSE, en ignorant explicitement le reste. Un modèle à
  //    qui l'on demande tout à la fois survole tout ; à qui l'on demande une
  //    chose, il la fait bien.
  //  · LA LÉGENDE AVANT TOUT. Les conventions graphiques varient d'un
  //    dessinateur à l'autre : les supposer, c'est se tromper sur tout le
  //    reste. On lit d'abord le cartouche et la légende, et on s'y tient.
  //  · TOUTE MESURE DIT SA SOURCE, par ordre de fiabilité décroissante : cote
  //    lue, déduction par proportion, estimation d'après un étalon, non
  //    mesurable. Un chiffre sans provenance n'a rien à faire dans un devis.
  //  · UNE SYNTHÈSE QUI SE JUGE : ce qui manque, ce qui est à vérifier sur
  //    place, et si le relevé est exploitable tel quel. Un relevé qui ne dit
  //    pas ses trous se fait prendre pour un relevé fini.
  //
  // Le raccourci PRÉREMPLIT : on relit, on ajuste au dossier, on joint le
  // plan, on envoie. Il complète le préprompt de `agent2.VISION_PROMPT`, qui
  // s'applique à toute image ; il ne le répète pas.
  { libelle: "Chiffrer un plan",
    prompt: `Je joins un plan. Prépare-moi un relevé exploitable pour le chiffrage.

Procède en six étapes SÉPARÉES, dans cet ordre. À chaque étape, traite SON sujet et ignore ce qui relève des autres : c'est ce qui évite de survoler.

1. CARTOUCHE ET LÉGENDE, avant tout le reste.
Lis le cartouche (titre, échelle, date, indice, auteur du plan) puis la légende, trame par trame et symbole par symbole : hachures de revêtement, symboles de sujets plantés, tracés de réseaux. La légende prime toujours sur une convention supposée : elle change d'un dessinateur à l'autre. Termine en désignant l'ÉTALON qui servira à mesurer (façade cotée, baie vitrée, place de voiture, largeur d'allée) et donne sa valeur.

2. ZONES DU TERRAIN.
Recense TOUTES les zones en balayant méthodiquement, secteur par secteur : nord-ouest, nord-est, centre, sud-ouest, sud-est. Pour chacune : nom ou usage (terrasse, pelouse, massif, allée, stationnement, potager, abords de piscine), exposition, et surface si elle est cotée. N'oublie aucune bande de terrain, ni les accès de service, ni les limites séparatives.

3. EXISTANT ET NATURE DES SOLS.
Pour chaque zone de l'étape 2, nommée : revêtement ou couvert actuel, état, dénivelé apparent, existant à déposer ou à conserver, contraintes de sol (remblai, enrochement, racines, réseaux visibles).

4. QUANTITÉS, CHACUNE AVEC SA SOURCE.
Surfaces (m²), linéaires (ml) et unités : terrasses, allées, engazonnement, massifs, bordures, murets, clôtures, portails, arrosage, éclairage, sujets à planter. Pour chaque quantité, dis d'où elle vient, dans cet ordre de préférence :
- cote lue sur le plan : reprends-la telle quelle ;
- déduction par proportion à partir d'une cote lue : montre le calcul ;
- estimation d'après l'étalon de l'étape 1 : rappelle l'étalon et sa valeur ;
- rien de tout cela : écris « non mesurable » et n'avance aucun chiffre.

5. POINTS SINGULIERS ET CONTRAINTES.
Ce qui coûte sans apparaître dans une surface : dénivelés et marches, accès des engins, évacuation des déblais, réseaux enterrés, mitoyenneté, arbres à protéger, phasage, saison de plantation.

6. SYNTHÈSE.
Un tableau des quantités par poste : quantité, unité, fiabilité de la mesure. Puis dis-moi ce qui manque pour chiffrer vraiment, ce qu'il faut vérifier sur place, et si ce relevé est exploitable tel quel ou s'il demande une visite. Ne donne aucun prix.` },
]
