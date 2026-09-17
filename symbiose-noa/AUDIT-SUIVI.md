# Suivi de l'audit détaillé du 15/09 — Symbiose Paysage

Branche `audit/symbiose` (worktree `infra IA/SYMBIOSE-audit`), partie de `2989872`.
Document source : « Audit détaillé - Duret et Symbiose.docx » (copie dans
`infra IA/sauvegardes/2026-09-16-avant-audit/`). Les fiches S-00 à S-27 sont le miroir
des fiches D : le socle est porté de `audit/duret`, ce qui diverge est réécrit pour
Symbiose (Drive, Outlook/Gmail, visuels, liens de connexion).

Règles de Noa (16/09) : lot par lot (un lot + ses bancs → validation et déploiement par
Noa → lot suivant) ; opérations serveur = scripts + procédures que Noa lance ; branches
poussées sur benit seulement.

## Lot 1 — premier lot court + garde-fous

| Fiche | Sujet | État |
|---|---|---|
| S-02 | Styles Word conservés au remplacement, contrôle du fichier produit | fait (bancs réels) |
| S-05 | Échecs métier jamais présentés comme réussis | étape 1 faite (normaliseur, exécuteur, boucle, reprise) ; reçus avant « créé/envoyé » et preuves par requête : lot suivant |
| S-03 | Bearer jamais envoyé à une origine externe ; propriété des visuels | étape 1 faite (jeton par origine, propriétaire noté au dépôt, route et pièces jointes contrôlées, pièce de mail résolue dans sa boîte, script de rattachement des anciens) ; registre PostgreSQL des ressources, médias DOCX, résultat structuré d'image manquante : lot suivant |
| S-22 | Export CSV neutralisé, export borné, secrets dans les traces | étape 1 faite (cellules inertes, fin bornée + pagination par clé + manifeste, ticket de téléchargement, filtre des secrets sur les handlers et les traces) ; carte des sorties, modes de confidentialité et rétention par type : lot 4 |
| S-23 / S-26 / S-00 | Scripts de sauvegarde, de déploiement vérifié et procédure de recette | fait (backup.sh complet et vérifié, restaurer.sh isolé, deploy.sh réordonné avec ligne de base vérifiée, readiness séparée de la liveness, RECETTE-LOT1.md) ; exercice de restauration réel : à jouer par Noa |
| S-27 | Drive complet et à jour | étape 1 faite (journal `changes` avec curseur, suppressions et sorties de périmètre appliquées, classeurs multifeuilles, dépôt réconcilié, copie reconnue au contenu) ; réconciliation périodique des ACL, octets natifs aux trames, écran des curseurs : lot suivant |
| S-06 | Secours lexical quand les embeddings tombent | étape 1 faite (embedding et voie vectorielle isolés, diagnostic, panne ≠ absence) ; orchestrateur de sources et comparables Drive : lot 2 |

## Lot 2 — documents durables, sources retrouvables, droits et recherche

| Fiche | Sujet | État |
|---|---|---|
| S-04 | Versions de documents et atelier durables | fait (verrou, écriture atomique, compteur réconcilié, lignée et manifeste, purge par groupe, quota qui refuse au lieu d'effacer) |
| S-07 | Références de sources stables | étape 1 faite (registre durable des messages et pièces, relu après redémarrage) ; couverture des recherches et registre en base : lots suivants |
| S-01 | Choisir et réutiliser le bon document de référence | fait (référence du travail mémorisée, remplacements déjà donnés repris, original modifié signalé) |
| S-09 | Droits appliqués avant les résultats et les comptes | étape 1 faite (boîtes dans la requête, comptes alignés, post-filtre gardé en défense) ; versions d'ACL et dérivés : lot suivant |
| S-08 | Réindexer sans effacer prématurément | étape 1 faite (bascule en une transaction, texte vide sans effet) ; générations et provenance fine : lot suivant |
| S-10 | Lire complètement les mails | étape 1 faite (pagination `@odata.nextLink`, plafond dit) ; delta, capacités métier, brouillons serveur : lot suivant |
| S-11 | Envois et approbations sans doublons | étape 1 faite (registre des opérations, réclamation avant l'appel, effet inconnu jamais relancé) ; figement des pièces par révision : lot suivant |
| S-13 | Fil de travail, pas de double demande | étape 1 faite (request_id des deux transports, résumé périmé écarté, mode du checkpointer dans la readiness) ; état de travail structuré : lot suivant |
| S-16 | Latence bornée, fournisseurs utilisables | étape 1 faite (budget de demande, pannes classées, demi-ouverture) ; propagation du budget à tous les étages : lot suivant |
| S-17 | Embeddings et files fiables | étape 1 faite (bail des jobs, identité du modèle sur le vecteur) ; générations de vecteurs : lot suivant |
| S-12 | Chiffres calculés, jamais devinés | étape 1 faite (montants en décimal, au centime) ; provenance ligne à ligne : lot suivant |
| S-14 | Apprendre sans mémoriser les erreurs | étape 1 faite (type, confiance, statut, panne passagère écartée, rappel par confiance) ; écran des leçons : lot suivant |
| S-15 | Skills générés testés et isolés | fait (même verrou d'effet, refus du code non isolé, retour arrière explicite) ; exécuteur isolé à fournir par l'exploitant |
| S-18 | Travaux lourds séparés | étape 1 faite (rôle de processus, requalification seulement sans signe de vie) ; baux durables par job long : lot suivant |
| S-21 | Secrets et navigateur | étape 1 faite (SSRF : résolution DNS, IPv6, adresses internes) ; secrets du worker et route interne : à faire avec le serveur |
| S-25 | Mesurer les usages et prouver l'absence de régression | fait (`scripts/recette_usages.py` : PASS/FAIL/SKIP, rapport daté par commit) |
| S-19 | Sessions et connexions Google | étape 1 faite (jetons au coffre, état OAuth à usage unique, essais bornés par origine, capacités par scope, lien jamais imprimé sur un serveur) ; réauthentification renforcée des gestes sensibles : lot suivant |
| S-24 | Vision cohérente avec la demande | étape 1 faite (pages choisies d'après la question, pages lues dites, suite du tour nommée et confrontée au registre) ; recadrage des cotes et mesures reliées à leur zone : lot suivant |
| S-20 | Cloisonnement PostgreSQL effectif | script de contrôle en lecture + procédure ; bascule du rôle applicatif : à faire par Noa sur le serveur |

## Journal

- 16/09 — S-02 : `bureautique/trame.py` réécrit le remplacement Word nœud `w:t` par nœud
  (styles des fragments, dessins, champs, zones de texte, tableaux imbriqués, en-têtes de
  première page) ; remplacements simultanés, chevauchements refusés ; formules Excel jamais
  réécrites ; `bureautique/controle.py` compare original et résultat rouvert. Bancs
  `test_trame_document` (+13), `test_reproduire_du_serveur`, `test_trame_pdf`,
  `test_charte_document` verts avec python-docx / openpyxl / PyMuPDF réels.
- 16/09 — hors fiche (trouvé par la suite de bancs) : relances de facturation comptées au
  jour UTC — entre minuit et 2 h « relancée à l'instant » devenait « il y a 1 jour ». Le
  jour se compte à Paris (`aujourd_hui_local`, `_jour_local`).
- 16/09 — S-05 (étape 1) : `skills/resultats.py` (outcome, ok, effect_status, evidence_refs,
  warnings, retryable) ; `execute_skill` rend `ok` métier + les champs d'avant, l'audit
  enregistre l'échec ; `tools_node` et la reprise après accord suivent `ok` au lieu de
  « le skill n'a pas levé ». Banc `test_resultats_normalises` (20).
- 16/09 — S-06 (étape 1) : `vectorstore/rag.py` calcule le vecteur HORS du `try` de la
  recherche — une panne d'embedding ne vidait plus seulement la voie vectorielle, elle
  renvoyait « aucun document ». La voie plein texte répond seule, la raison est dite, et
  une panne n'est plus présentée comme une absence. Banc `test_recherche_documents`.
- 16/09 — S-03 (étape 1) : `frontend/lib/origineBackend.ts` — le jeton de session n'est
  posé QUE si l'URL du fichier vise l'origine du backend (`ApercuDocument`, `FileCard`) ;
  une adresse absolue étrangère recevait le bearer. Le dépôt de visuels note le
  PROPRIÉTAIRE (nouveau module `security/lecteur.py` : l'identité posée une fois au goulot
  `execute_skill` et à la préparation des pièces, relue au dépôt) ; `routers/visuels.visuel`
  et la résolution d'une pièce jointe vérifient ce propriétaire — un identifiant connu ne
  vaut plus autorisation. Une pièce de mail se résout DANS SA BOÎTE.
  `scripts/rattacher_visuels.py` rattache les anciens fichiers (constat par défaut).
  Bancs `test_visuels_proprietaire` (nouveau), `test_pieces_multiples`,
  `test_image_dans_document`, `test_pieces_jointes`, `test_apercu_pieces`,
  `test_vision_reponse` verts ; `tsc --noEmit` vert.
- 16/09 — S-22 (étape 1) : `security/secrets.py` — le filtre était posé sur des LOGGERS,
  or les enregistrements traversent les HANDLERS : il ne voyait presque rien. Il est posé
  sur les handlers (et sur les loggers, en défense), masque le message formaté, les
  arguments, le texte d'exception et la pile. L'export de la console neutralise les
  cellules qui commencent par `= + - @` (OWASP), rend le CSV en flux par clé (plus de
  `OFFSET` qui glisse pendant la pagination), et finit par un `#manifeste` qui dit combien
  de lignes ont été écrites. Bancs `test_secrets_journaux`, `test_echanges_admin`.
- 16/09 — S-23 / S-26 / S-00 : `backup.sh` sauvegarde la base ET le volume des documents
  produits (les visuels, l'atelier) et les secrets — chiffrés si `BACKUP_PASSPHRASE` ;
  un jeu s'écrit à côté et n'est publié qu'entier, avec manifeste et empreintes.
  `restaurer.sh` monte une copie ISOLÉE (autre projet compose, autres ports, clés vidées,
  comptes Google effacés, tâches coupées). `deploy.sh` : version livrée → images →
  sauvegarde → base seule → migrations (un échec ARRÊTE) → schéma vérifié → bascule →
  `/api/ready`. La ligne de base des migrations est VÉRIFIÉE objet par objet
  (`attendus.tsv`) au lieu d'être marquée en bloc. `/api/health` (liveness) et
  `/api/ready` (readiness) sont enfin deux choses différentes. Banc `test_deploiement`.
- 16/09 — S-27 (socle) : `vectorstore.copier_source` — un fichier au contenu IDENTIQUE à
  un autre reprend ses morceaux et ses vecteurs sous SA source, SON nom et SON niveau
  d'accès ; ni relecture, ni OCR, ni embedding payés deux fois.
- 16/09 — hors fiche, trouvé en portant : `restaurer.sh` écrivait `reglages (nom, …)`
  alors que la colonne s'appelle `cle` — et comme les coupures partaient dans UN SEUL
  `psql -c`, donc une seule transaction, l'échec annulait aussi le `DELETE FROM cles_api`.
  Une copie restaurée gardait ses clés. Coupures séparées, et les comptes Google reliés
  (refresh tokens vers le vrai Drive) sont effacés eux aussi. **Corrigé des deux côtés.**
- 16/09 — S-04 : `bureautique/atelier.py` — fiche et contenu étaient deux écritures
  séparées : une interruption ou deux ajouts simultanés désynchronisaient le compteur et
  le texte. Verrou par document, écriture par fichier temporaire puis `os.replace`,
  compteur RÉCONCILIÉ depuis le contenu réel. Chaque document porte sa lignée
  (`document_id`, `revision_id`, `parent_revision_id`, `thread_id`) et un manifeste
  (format, source, substitutions, images, ce qui reste à compléter) ; la purge se fait par
  GROUPE après vérification des références, et le quota refuse au lieu d'effacer un
  brouillon. Banc `test_versions_documents`.
- 16/09 — S-07 (étape 1) : `ressources/registre.py` — un registre DURABLE (JSON atomique
  dans DOCUMENTS_DIR, borné, jamais le contenu) : après un redémarrage, la `ref` d'un mail
  ou d'une pièce jointe se retrouve encore. Avant, elle vivait dans un dictionnaire de
  processus et « ouvre la pièce jointe » tombait sur un mail au hasard.
- 16/09 — S-01 : la référence choisie pour un travail est mémorisée (source, empreinte,
  raison) ; les remplacements déjà donnés sont repris dès que l'inspection les confirme —
  on ne redemande plus ce qui a été dit —, et un original modifié depuis le choix est
  SIGNALÉ. Bancs `test_livrable`, `test_compte_rendu`, `test_livrables_pertinents`,
  `test_reproduire_du_serveur` verts.
- 16/09 — S-09 / S-08 / S-10 / S-11 / S-13 / S-16 / S-17 / S-20 : les boîtes autorisées
  entrent DANS la requête SQL (en paramètre) au lieu d'un post-filtre appliqué après coup —
  le compte suivait l'un et la liste l'autre ; liste vide = fail-closed. Une réindexation
  supprime et réinsère dans LA MÊME transaction, et un texte vide ne remplace plus une
  version valide. La synchronisation Outlook suit `@odata.nextLink` et DIT quand elle
  s'arrête sur son plafond. `skills/operations.py` + migration **045** : un effet externe
  s'inscrit avec sa décision et son empreinte, se RÉCLAME une fois (UPDATE conditionnel),
  et une réponse perdue devient « effet inconnu » — jamais une relance. `agents/requetes.py`
  + migration **046** : un `request_id` réclamé une seule fois, quel que soit le transport
  (WS puis HTTP ne lancent plus deux tours). `llm/budget.py` : le temps de la DEMANDE se
  compte une fois, les pannes sont classées (configuration / quota / réseau) et la cascade
  entièrement écartée ne rouvre qu'UN candidat. Migration **047** : un job de vectorisation
  porte son bail (`FOR UPDATE SKIP LOCKED`) et le vecteur porte le modèle qui l'a produit.
  `scripts/controle_droits_base.py` : contrôle en LECTURE du cloisonnement PostgreSQL.
  Bancs `test_droits_et_reindexation` (nouveau), `test_budget_et_baux` (nouveau),
  `test_disjoncteur`, `test_resume_en_fond`, `test_vitesse_tour`, `test_recherche_documents`,
  `test_graphe_routeurs`, `test_accord_et_fil` verts.
- 16/09 — S-12 / S-14 / S-15 / S-18 / S-21 / S-25 : les montants s'additionnent en
  `Decimal` au centime (`_agreger`) — en flottant, un total de trois cents lignes ne
  tombait plus juste. Une leçon porte son type, sa confiance et son statut (migration
  **048**), les plus sûres sont rappelées d'abord, et une correction qui suit une panne
  passagère n'en produit plus. Un skill GÉNÉRÉ passe par le même verrou d'effet que les
  natifs et n'est plus exécuté dans un sous-processus du backend : sans exécuteur isolé,
  il est refusé, en le disant (`autoriser_code_non_isole` pour revenir en arrière).
  `role_processus` commande les boucles de fond — un second processus ne relance plus les
  mêmes travaux — et le démarrage ne requalifie que ce qui n'a plus donné signe de vie
  depuis un quart d'heure. La garde du navigateur RÉSOUT le nom (IPv6, IPv4 déguisée,
  169.254.169.254, nom public qui mène à 10.x) au lieu de comparer des chaînes.
  `scripts/recette_usages.py` joue tous les bancs et rend un rapport daté PASS/FAIL/SKIP
  par commit : **138 PASS · 0 FAIL · 3 SKIP** sur cette branche. Banc
  `test_chiffres_et_isolement` (22).
- 16/09 — S-19 (étape 1, propre à Symbiose) : le jeton de rafraîchissement d'un compte
  Google — une clé PERMANENTE vers son Drive et sa boîte — était écrit en clair.
  `security/coffre.py` le chiffre au repos avec une clé SÉPARÉE du secret des sessions
  (`JETONS_CHIFFREMENT_CLE`) ; les lignes d'avant restent lisibles et sont remises au
  coffre à l'usage, sans migration ; une clé changée rend « illisible », jamais une
  chaîne inutilisable. L'état OAuth, signé et daté, était REJOUABLE dix minutes : il
  porte désormais une marque consommée à la vérification. Les demandes de lien de
  connexion et les essais de vérification sont bornés par ORIGINE (`security/tentatives.py`)
  — et la réponse ne change pas quand la borne mord, sinon elle apprendrait quelles
  adresses existent. Les CAPACITÉS suivent les droits rendus par Google : lire le Drive
  ne donne plus le droit d'y écrire ni de poser un brouillon Gmail, et le refus dit quoi
  faire au lieu d'un 403 d'API. Enfin le lien de connexion ne s'imprime plus dès que
  `DEBUG` est vrai : l'ENVIRONNEMENT fait foi. Banc `test_connexions_google` (36).
- 16/09 — S-27 (étape 1, propre à Symbiose) : la synchronisation comparait des DATES —
  or un fichier supprimé, mis à la corbeille, déplacé hors périmètre ou dont l'accès a été
  retiré n'en change aucune : il disparaissait du listage et restait en mémoire.
  `ingestion/drive_changes.py` lit le JOURNAL de Google (`changes.list`) depuis un curseur,
  retire ce qui a disparu ou est sorti du périmètre, réingère ce qui a changé — et le
  curseur ne s'écrit qu'APRÈS le traitement (une panne fait rejouer, elle ne fait jamais
  sauter). Un curseur périmé renvoie à un inventaire, en le disant ; un inventaire TRONQUÉ
  n'en pose pas. Un Google Sheet s'exporte désormais en XLSX et non en CSV, et
  `parsers.lire_excel` lit TOUTES les feuilles en gardant leur nom — un classeur de trois
  onglets n'entre plus amputé des deux tiers. Enfin un dépôt dont la réponse réseau se perd
  est RÉCONCILIÉ (on regarde si le fichier est arrivé avant de conclure) et rend son
  empreinte : plus de doublon, et plus de « existe déjà, donne un autre nom » pour un dépôt
  qui avait réussi. Bancs `test_drive_complet` (nouveau, 27), `test_tableau_joint` (+5),
  `test_depot_drive`, `test_drive_increment` verts.
- 16/09 — S-24 (étape 1, socle des deux côtés) : on rendait les CINQ PREMIÈRES pages d'un
  PDF, toujours. Sur un dossier de quarante pages, la cote demandée est page 8 et le
  quantitatif page 23 : l'assistant répondait « non visible » après avoir lu la page de
  garde et trois pages de clauses — sans dire qu'il n'en avait lu que cinq. La couche
  texte se lit en quelques millisecondes : elle sert à CLASSER les pages par rapport à la
  question, la page 1 restant toujours lue (cartouche, échelle, affaire). Sans question
  utile, sans couche texte ou sur un document court, rien ne change. L'en-tête dit
  désormais les NUMÉROS des pages montrées et demande d'en réclamer une plutôt que de
  l'estimer. Enfin la suite du tour est NOMMÉE (`vision_suite` : document, retouche,
  retouche_indisponible, aucune) et confrontée au registre réel des capacités — chez le
  jumeau, sans moteur de retouche, une demande de photomontage ne passe plus la main.
  Banc `test_pages_et_suite` (25, le même fichier des deux côtés).


## Contre-vérification complémentaire — 16/09

Voir `REVUE-COMPLEMENTAIRE-20260916.md`. Plusieurs défauts supplémentaires ont été corrigés et testés localement. Les mentions « fait » ci-dessus ne valent pas validation en production ; les éléments annoncés « étape 1 » et « lot suivant » restent partiels. Aucun déploiement effectué dans cette revue.


## Continuation de fiabilisation — 16/09

Voir `FIABILISATION-20260916.md` : dépendances corrigées/verrouillées, migration 049, reprise du chat, sources directes, copies des pièces avant accord, documents et références entre processus, apprentissage filtré et démarrage renforcé. Modifications locales non déployées. Les mentions « fait » précédentes ne remplacent pas la recette réelle ; les points partiels sont explicitement recensés dans cette mise à jour.
