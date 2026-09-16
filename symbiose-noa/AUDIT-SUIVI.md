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
| S-27 | Drive complet et à jour | socle fait (une copie reconnue à son contenu reprend les morceaux de l'original) ; suivi `changes`, export XLSX multifeuille, dépôt réconcilié : lot propre à Symbiose |
| S-06 | Secours lexical quand les embeddings tombent | étape 1 faite (embedding et voie vectorielle isolés, diagnostic, panne ≠ absence) ; orchestrateur de sources et comparables Drive : lot 2 |

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
