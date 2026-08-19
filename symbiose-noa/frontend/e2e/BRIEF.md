# Brief client — Infrastructure IA métier Symbiose Paysage

Référence du banc de recette (`recette.json`, champ `reference`). Texte remis
par Noa Benitez le 19/08/2026, reproduit tel quel ; les sections numérotées
sont celles citées par les contrôles.

## 1. Contexte général
Symbiose Paysage souhaite mettre en place une infrastructure IA métier pour centraliser, organiser et exploiter l'ensemble des informations clés de l'entreprise. L'objectif n'est pas de déployer un simple assistant conversationnel, mais de construire une véritable infrastructure logicielle autour de deux agents IA spécialisés, capables de travailler sur une mémoire commune et d'assister les équipes sur plusieurs volets : commercial, administratif, études, conception, production, visuels et chiffrage.

## 2. Sources d'information identifiées
Extrabat, DegTime, Google Drive, Messageries, Dossiers clients, Historiques de devis, Historiques de chantiers, Photos de chantier, Plans PDF / cadastraux / d'architecte, Fichiers SketchUp, Documents administratifs, Catalogues fournisseurs / méthodes internes de chiffrage à confirmer. Le problème principal n'est pas l'absence de données, mais leur dispersion.

## 3. Objectif du projet
Mémoire d'entreprise centralisée, interrogeable depuis une interface unique. Les collaborateurs doivent pouvoir : retrouver rapidement un devis, un chantier, un client ou une information ; mieux suivre les demandes clients ; préparer plus rapidement les devis ; exploiter photos, plans et fichiers existants ; générer des visuels paysagers ; préparer les bases d'un pré-chiffrage ; réduire le temps administratif ; améliorer la transmission d'information. Un copilote d'entreprise, pas une collection d'outils.

## 4. Architecture cible
Interface unique ; deux agents IA métier ; mémoire commune ; sous-agents spécialisés ; couche d'orchestration ; supervision humaine ; reporting des usages et des gains. Les deux agents doivent pouvoir dialoguer entre eux : une demande reçue par l'agent commercial peut déclencher une analyse de plan ou de photo par l'agent conception, dont les résultats remontent vers l'agent administratif.

## 5. Agent 1 — Mémoire, commercial et administratif
Point d'entrée principal de l'information interne : recherche dans les dossiers clients ; historiques de devis et de chantiers ; informations administratives ; traitement des emails entrants ; classification et priorisation des demandes ; proposition de réponses ; préparation des éléments d'un devis ; suivi des dossiers clients ; conservation de l'historique des échanges. Configuré selon les méthodes internes (organisation des dossiers, modèles, règles de gestion, niveaux d'accès). **Il ne doit pas inventer d'information. Lorsqu'une donnée manque, il devra faire apparaître [À COMPLÉTER].**

## 6. Agent 2 — Conception, visuels et production
Analyse de plans PDF, cadastraux ou architecte ; analyse de photos terrain ; exploitation des fichiers SketchUp ; recherche de projets similaires ; génération de visuels paysagers via Higgsfield ; simulations avant / après ; variantes d'aménagement ; aide au chiffrage ; extraction de postes de travaux ; listes de tâches ; bases de pré-devis. **L'agent ne doit pas valider seul un chiffrage** : la décision finale reste humaine.

## 7. Technologies et intégrations
Extrabat (API coûteuse ou limitée, à analyser ; migration Sellsy envisageable), DegTime, Google Drive, Messageries, SketchUp, Higgsfield, API IA à l'usage pour plans et photos. À confirmer avec les dirigeants : accès Extrabat, exports, accès Drive, organisation des fichiers, messageries, formats SketchUp, volume, fréquence, budget API.

## 8. Mémoire d'entreprise et RAG
Cœur du projet. Retrouver les bonnes informations dans les documents internes (devis, photos, plans, échanges, historiques, administratif, méthodes). Architecture RAG. Recherche intelligente même quand l'utilisateur ne formule pas les bons mots — exemple : « Retrouve-moi un chantier similaire réalisé à Arcachon avec une terrasse bois. »

## 9. Points de vigilance
Qualité des données ; droits d'accès par utilisateur ; informations sensibles ; fiabilité des exports ; limites de l'analyse IA sur plans et photos ; **validation humaine obligatoire sur les devis** ; gestion des erreurs ; **traçabilité des actions** ; coût des API ; adoption ; maintenance. L'IA prépare, accélère, organise, assiste ; les décisions engageantes restent validées par les équipes.

## 10. Travail attendu côté Pluton / NOA
Cadrage projet, questions aux dirigeants, cas d'usage prioritaires, cartographie des outils, accès, quick wins, dépendances, roadmap, setup initial vs suivi mensuel, zones floues.

## 11. Questions à poser aux dirigeants
Trois problèmes urgents ; où le temps se perd ; documents les plus recherchés ; usages Extrabat ; exports ; organisation Drive ; types de plans/photos ; SketchUp ; qui valide les devis ; informations à ne jamais générer ; collaborateurs et droits ; volume initial ; reporting mensuel ; priorité (administratif, commercial, conception, visuels, chiffrage).

## 12. Périmètre commercial actuel
Investissement initial 14 800 € HT ; forfait mensuel 450 € HT ; deux agents interconnectés ; mémoire d'entreprise ; intégrations prioritaires ; formation ; pilotage et optimisation ; reporting mensuel ; API IA à l'usage non incluses. Option pôle commercial / prospection hors périmètre.

## 13. Projection ROI
Temps valorisé 65 €/h. Mois 1 : 35–45 h ; mois 2 : 50–65 h ; mois 3 : 65–90 h ; mois 6 : 70–95 h ; mois 12 : 75–100 h. ROI net 12 mois : 31 000 à 49 000 €. À présenter comme des estimations.

## 14. Conclusion
Une infrastructure métier pour structurer la connaissance interne, fluidifier les opérations et accompagner la croissance : moins de temps à chercher, trier, reconstituer, préparer.

## 15. Gestion des accès, sécurité et gouvernance
**Profils** : Dirigeants, Responsables de service, Conducteurs de travaux, Bureau d'études, Administratif, Commerciaux, Collaborateurs terrain, Administrateur technique — chacun n'a que les fonctionnalités et informations nécessaires.
**Tableaux de bord différenciés** — Direction : vision globale, reporting, ROI, pilotage des agents, validation des actions importantes, statistiques d'utilisation, gestion des utilisateurs, paramétrage. Collaborateurs : dossiers les concernant, recherche documentaire, assistance métier, informations autorisées, historique de leurs propres échanges. Pas d'accès aux données stratégiques (marges, indicateurs financiers, statistiques globales, configuration des agents, droits) sauf autorisation.
**Horaires d'utilisation** : règles par plages horaires (ex. lundi–vendredi 7h–19h), exceptions pour dirigeants, entièrement paramétrable.
**Contrôle des usages** : journalisation des actions ; consommation par utilisateur ; coûts IA ; usages anormaux ; limitation du nombre de requêtes selon les profils.
