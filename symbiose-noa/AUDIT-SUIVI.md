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
