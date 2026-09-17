# L'audit sur Symbiose — ce qu'il faut faire, dans l'ordre, et ce qu'on doit voir

Branche `audit/symbiose`. Ce document est la **procédure** : les commandes se lancent
sur le serveur (Noa), les contrôles se font à l'écran. Rien ici n'a tourné contre le
vrai Postgres, le vrai Drive ni un navigateur — c'est précisément ce que cette recette
va dire.

Fiches livrées sur cette branche, dans l'ordre des commits :

**Lot 1** — **S-02** (styles Word), **S-05** (un échec n'est plus une réussite), **S-06**
(recherche quand les embeddings tombent), **S-03** (propriété des visuels, jeton),
**S-22** (journaux et export), **S-23 / S-26 / S-00** (sauvegarde, déploiement,
restauration).

**Lot 2** — **S-04** (versions et atelier durables), **S-07** (références stables),
**S-01** (bon document de référence), **S-09** (droits dans la requête), **S-08**
(réindexation), **S-10** (pagination des mails), **S-11** (un envoi ne part qu'une fois),
**S-13** (une demande ne lance qu'un tour), **S-16** (budget de temps), **S-17** (baux de
vectorisation), **S-20** (cloisonnement PostgreSQL), **S-12** (montants au centime),
**S-14** (leçons qualifiées), **S-15** (code généré isolé), **S-18** (rôle du processus),
**S-21** (SSRF du navigateur), **S-25** (la recette qui se mesure), **S-19** (jetons
Google au coffre, état OAuth, bornes), **S-27** (Drive : changements, onglets, dépôt),
**S-24** (pages d'un PDF, suite du tour).

---

## 1. Avant de déployer (S-00 — la préparation)

1. **Pousser la branche** (Claude ne pousse pas) :
   `git push origin audit/symbiose` depuis le worktree `SYMBIOSE-audit`.
2. **Un réglage à poser dans le `.env` du serveur** (audit S-19) :
   ```
   JETONS_CHIFFREMENT_CLE=<openssl rand -hex 32>
   ```
   Elle chiffre au repos les jetons des comptes Google reliés, **séparément** du
   secret des sessions : changer `JWT_SECRET_KEY` ne doit pas couper les comptes.
   Vide, tout continue de fonctionner (dérivation depuis le secret JWT) ; posée,
   les jetons se réécrivent avec elle au fil des lectures.
3. **Optionnel mais recommandé** : `BACKUP_PASSPHRASE=<phrase>` (chiffre les
   secrets dans les sauvegardes) et `BACKUP_DISTANT=user@hote:/chemin` (copie hors
   de la machine). La phrase de passe se garde **ailleurs** que les sauvegardes.
4. **Facultatif, pour plus tard** : `ROLE_PROCESSUS` (audit S-18) reste à
   `complet` — ne le changer que le jour où l'on ajoute un second processus.

## 2. Déployer (S-26 — la livraison vérifiée)

```bash
cd ~/SYMBIOSE/symbiose-noa        # le dossier du projet sur le VPS
git fetch origin && git checkout audit/symbiose && git pull
./deploy.sh
```

`deploy.sh` fait, **dans cet ordre** : version livrée → construction des images →
**sauvegarde** → démarrage de la base seule → **migrations** (un échec ARRÊTE la
livraison) → vérification que le schéma est complet → bascule → attente de
`/api/ready`.

⚠️ **Cinq migrations nouvelles** — **045**, **046**, **047**, **048**, **049**. Toutes additives et
idempotentes ; `deploy.sh` les applique seul, et un échec ARRÊTE la livraison
(l'ancienne version reste en service). Elles ajoutent le registre des opérations
externes (045), celui des demandes de chat (046), les baux de vectorisation et
l'identité du modèle sur le vecteur (047), la qualification des leçons (048), et le propriétaire / signe de vie des demandes (049).

⚠️ `deploy.sh` va aussi, pour la première fois, **vérifier objet par objet** que les
migrations déjà suivies sont bien en place (`attendus.tsv`). S'il annonce « objet
ABSENT → elle sera jouée » pour une migration ancienne, c'est un trou réel du schéma
de production : **le relever avant de continuer**.

**À VÉRIFIER** : la dernière ligne affiche l'état prêt, avec le commit. Sinon, le
script dit ce qui manque et rappelle le retour arrière. Avant la bascule, un échec
arrête la livraison en conservant les conteneurs précédents. Après la bascule,
un échec de readiness exige un retour arrière explicite : il n'est pas automatique.

```bash
# la version réellement en ligne, à tout moment
curl -s https://symbiose.pluton-consulting.fr/api/ready | head -c 400
```

## 3. Ce qu'on doit voir, fiche par fiche

### S-03 — les visuels ont un propriétaire, le jeton ne voyage plus
1. Depuis deux comptes différents : le premier joint une photo au chat, le second
   ouvre l'URL `/api/visuels/<clé>` de cette photo.
   **À VÉRIFIER** : le second reçoit 404 (« visuel inconnu »), le premier la voit.
2. Rattacher les visuels d'avant le correctif (ils restent lisibles par défaut) :
   ```bash
   docker compose exec backend python scripts/rattacher_visuels.py            # constat
   docker compose exec backend python scripts/rattacher_visuels.py --ecrire   # rattache
   ```
   **À VÉRIFIER** : le constat dit combien de visuels ont un propriétaire établi et
   combien restent indéterminés. Les anciennes conversations montrent toujours leurs
   images.
3. Une image reçue en pièce jointe d'un mail, insérée dans un Word : elle entre (elle
   se résout maintenant dans SA boîte) ; depuis un compte sans droit sur cette boîte,
   elle est refusée en le disant.
4. Onglet **Réseau** du navigateur, sur un aperçu de document : la requête vers le
   backend porte `Authorization`, une adresse d'un autre domaine n'en porte **pas**.

### S-22 — journaux et export
1. Console développeur → **Exporter tout (Excel)**.
   **À VÉRIFIER** : le téléchargement démarre tout de suite (plus d'attente pendant
   que le navigateur charge tout en mémoire) ; la dernière ligne du CSV est un
   `#manifeste` avec le nombre de lignes ; une question commençant par `=` apparaît
   en texte, pas en formule.
2. `docker compose logs backend | grep -i "key="` → aucune clé lisible, seulement
   `***` suivi de six caractères.

### S-05 / S-06 — les gestes disent la vérité
1. Poser une question qui déclenche un geste voué à l'échec (par exemple retenir une
   consigne vide). **À VÉRIFIER** : l'assistant dit l'échec ; la console le compte
   comme un échec, pas comme une réussite.
2. Couper la clé Google (Paramètres → Clés API) et chercher dans les documents.
   **À VÉRIFIER** : la recherche répond quand même (voie plein texte) et dit que la
   recherche par sens est indisponible — jamais « je n'ai rien trouvé ».

### S-02 — les documents gardent leur mise en page
Reprendre un devis Word du Drive et remplacer un nom.
**À VÉRIFIER** : logo, en-tête, styles et tableaux intacts ; seule la valeur demandée
a changé ; l'assistant dit ce qu'il n'a pas pu remplacer.

### S-19 — les connexions Google
1. Paramètres → Mon compte Google : relier un compte, puis
   `SELECT left(refresh_token, 8) FROM connexions_google;` sur le serveur.
   **À VÉRIFIER** : la valeur commence par `coffre1:`, jamais par `1//`.
2. Les comptes reliés AVANT ce déploiement continuent de marcher, et passent au
   coffre au premier rafraîchissement (journal : « Jetons Google mis au coffre »).
3. Ouvrir deux fois le même lien de retour Google (bouton Précédent du navigateur) :
   le second passage est refusé.
4. `docker compose logs backend | grep "MAGIC LINK"` → **rien** en production.

### S-27 — le Drive à jour
1. Lancer une synchronisation complète une fois (elle pose le curseur).
   **À VÉRIFIER** : le bilan dit `mode: inventaire` et `curseur_pose: true`.
2. Supprimer un fichier sur le Drive, puis relancer.
   **À VÉRIFIER** : `mode: changements`, et le fichier n'est plus cité par
   l'assistant. Une recherche sur son contenu ne le rend plus.
3. Un Google Sheet à trois onglets : « que contient <ce classeur> ? »
   **À VÉRIFIER** : les trois onglets sont cités, pas seulement le premier.

### S-24 — la page qu'il faut lire
Joindre un PDF long dont la cote utile est en page 8, et demander cette cote.
**À VÉRIFIER** : la réponse donne la cote OU dit explicitement quelles pages ont été
lues et que celle-là ne l'a pas été — jamais un « non visible » sans précision.

### Le reste du lot 2, en une passe
Ces fiches se voient à l'usage plutôt que par un geste dédié. En une conversation :

* **S-01 / S-04** — « reprends ce devis pour M. Martin », puis « change le prix »,
  puis « mets-le en pièce jointe d'un mail ». **À VÉRIFIER** : c'est la DERNIÈRE
  version qui part ; on ne redemande pas ce qui a déjà été dit.
* **S-09** — « combien de mails de <collègue> ? » depuis un compte qui n'a pas accès
  à cette boîte. **À VÉRIFIER** : le compte annoncé est celui qu'on a le droit de
  lire, jamais un total plus grand que la liste.
* **S-08** — relancer « Enrichir les documents ». **À VÉRIFIER** : aucun document ne
  perd ses morceaux en cours de route (une réindexation est une seule transaction).
* **S-11 / S-13** — approuver un envoi, puis recharger la page pendant le traitement.
  **À VÉRIFIER** : le mail ne part pas deux fois, et la demande ne relance pas un
  second tour.
* **S-12** — « le total des devis de l'année ». **À VÉRIFIER** : le total tombe juste
  au centime (recoupez sur trois lignes).
* **S-14** — corriger l'assistant après une réponse fausse, puis regarder
  Connaissances → Leçons. **À VÉRIFIER** : la leçon porte un type et une confiance ;
  une correction qui suit une panne (quota, délai) n'en crée AUCUNE.
* **S-16** — un tour qui enchaîne plusieurs gestes. **À VÉRIFIER** : il se termine,
  et une cascade entièrement en panne ne fait plus payer tous ses fournisseurs.
* **S-21** — « ouvre http://169.254.169.254/ ». **À VÉRIFIER** : refusé, en disant
  que l'adresse est interne.
* **S-25** — sur le serveur :
  `docker compose exec backend python scripts/recette_usages.py`.
  **À VÉRIFIER** : un rapport daté, et 0 FAIL.

## 4. L'exercice de restauration (S-23) — à faire une fois, au calme

```bash
./backup.sh                                            # un jeu complet, daté
./restaurer.sh ~/symbiose-backups/symbiose_<date>      # copie ISOLÉE, ports 3100/8100
```

**À VÉRIFIER dans la copie** (jamais dans la production) : une conversation passée
s'ouvre avec ses pièces jointes ; une trame se rouvre ; un document avec image montre
son image ; un brouillon de mail garde sa pièce jointe. Noter **le temps qu'a pris la
reprise** et **l'heure du dernier point restaurable** (manifeste du jeu) : c'est ce
couple qui dit ce que la maison peut perdre.

La copie ne peut **rien envoyer** : clés vidées dans son `.env` et dans sa base,
**comptes Google reliés effacés** (leurs jetons de rafraîchissement ouvriraient le
vrai Drive), tâches planifiées coupées.

```bash
./restaurer.sh --arreter                               # puis, si l'on veut, docker volume rm …
```

## 5. Retour arrière

* **Application** : `git checkout <commit précédent> && ./deploy.sh`. Les migrations
  de cette branche sont **additives** : l'ancienne image les ignore.
* **Code généré** (S-15) : `AUTORISER_CODE_NON_ISOLE=true` rétablit l'ancien
  comportement — en connaissance de cause, et cela se voit dans le journal.
* **Jetons Google** (S-19) : retirer `JETONS_CHIFFREMENT_CLE` fait retomber sur la
  dérivation d'avant ; les jetons déjà réécrits restent lisibles.
* **Base** : une restauration en production est une opération préparée — jamais un
  réflexe. Passer par la copie isolée d'abord.

## 6. Ce que ce lot ne prouve pas

* Aucune requête n'a tourné contre le vrai Postgres du serveur : le SQL de l'export
  et la ligne de base des migrations sont vérifiés par les bancs, pas par la
  production.
* Le Drive, la messagerie et les fournisseurs de modèles n'ont pas été appelés.
* Rien n'a été rendu dans un navigateur : l'export de la console et les aperçus de
  documents se jugent à la première utilisation.
* Les **étapes 2** annoncées fiche par fiche dans `AUDIT-SUIVI.md` ne sont pas
  faites : registre des ressources en base (S-03/S-07), générations de vecteurs
  (S-17), delta Graph des mails (S-10), réconciliation périodique des ACL Drive
  (S-27), recadrage des cotes (S-24), rétention et modes de confidentialité (S-22).
* La bascule du rôle applicatif PostgreSQL (S-20) est une opération de serveur :
  `scripts/controle_droits_base.py` dit seulement où l'on en est.

## Complément de fiabilisation du 16 septembre 2026

- Inclure `backend/requirements.lock` et la migration `049_requetes_signe_de_vie.sql` dans la livraison. La branche locale contient aussi des fichiers nouveaux non suivis tant que les corrections ne sont pas enregistrées dans Git.
- Construire le backend depuis le fichier verrouillé avec empreintes ; NumPy reste en version 1.x pour spaCy 3.7. Le frontend utilise Next 15.5.25, PostCSS 8.5.28 et Sharp 0.35.4.
- Le code backend de production est désormais dans l’image ; les secrets et les documents restent montés. Le montage intégral du code n’existe que dans `docker-compose.dev.yml`. Une simple réouverture du navigateur ne livre donc pas ces changements.
- Le signe de vie des requêtes bat toutes les 15 secondes ; une demande sans signe de vie depuis 120 secondes devient interrompue lors de sa consultation, sans relance automatique. Le budget total d’un tour est de 600 secondes (`DEMANDE_DELAI_S`).
- Les pièces jointes des nouveaux accords sont copiées avant validation, contrôlées par SHA-256 avant envoi et conservées sept jours. Après cette durée, préparer un nouvel accord.
- Une recherche sans résultat en mémoire complète la lecture avec le stockage et/ou la boîte autorisés, avec 15 secondes par source. Les noms trouvés doivent encore être ouverts ; cette recherche n’est pas exhaustive.
- Les tests de la dernière revue et leurs limites sont détaillés dans `FIABILISATION-20260916.md`. Ne pas classer la production validée avant la recette des services réels.
