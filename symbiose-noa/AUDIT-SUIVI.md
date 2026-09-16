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
