# Lot 1 de l'audit — ce qu'il faut faire, dans l'ordre, et ce qu'on doit voir

Branche `audit/symbiose`. Ce document est la **procédure** : les commandes se lancent
sur le serveur (Noa), les contrôles se font à l'écran. Rien ici n'a tourné contre le
vrai Postgres, le vrai Drive ni un navigateur — c'est précisément ce que cette recette
va dire.

Fiches livrées dans ce lot : **S-02** (styles Word), **S-05** (un échec n'est plus une
réussite), **S-06** (recherche quand les embeddings tombent), **S-03** (propriété des
visuels, jeton), **S-22** (journaux et export), **S-23 / S-26 / S-00** (sauvegarde,
déploiement, restauration).

---

## 1. Avant de déployer (S-00 — la préparation)

1. **Pousser la branche** (Claude ne pousse pas) :
   `git push origin audit/symbiose` depuis le worktree `SYMBIOSE-audit`.
2. **Optionnel mais recommandé** dans le `.env` du serveur :
   `BACKUP_PASSPHRASE=<phrase>` (chiffre les secrets dans les sauvegardes) et
   `BACKUP_DISTANT=user@hote:/chemin` (copie hors de la machine). La phrase de
   passe se garde **ailleurs** que les sauvegardes.

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

⚠️ **Ce lot n'apporte aucune migration** : le schéma ne bouge pas. Mais `deploy.sh`
va, pour la première fois, **vérifier objet par objet** que les migrations déjà
suivies sont bien en place (`attendus.tsv`). S'il annonce « objet ABSENT → elle sera
jouée » pour une migration ancienne, c'est un trou réel du schéma de production :
**le relever avant de continuer**, les migrations sont idempotentes mais la
constatation compte.

**À VÉRIFIER** : la dernière ligne affiche l'état prêt, avec le commit. Sinon, le
script dit ce qui manque et rappelle le retour arrière — l'ancienne version est
restée en service.

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

* **Application** : `git checkout <commit précédent> && ./deploy.sh`. Ce lot
  n'apporte aucune migration ; celles des lots suivants sont **additives**,
  l'ancienne image les ignore.
* **Base** : une restauration en production est une opération préparée — jamais un
  réflexe. Passer par la copie isolée d'abord.

## 6. Ce que ce lot ne prouve pas

* Aucune requête n'a tourné contre le vrai Postgres du serveur : le SQL de l'export
  et la ligne de base des migrations sont vérifiés par les bancs, pas par la
  production.
* Le Drive, la messagerie et les fournisseurs de modèles n'ont pas été appelés.
* Rien n'a été rendu dans un navigateur : l'export de la console et les aperçus de
  documents se jugent à la première utilisation.
* Les fiches restantes (S-01, S-04, S-07 à S-21, S-24, S-25, S-27, et la suite de
  S-03, S-05, S-06, S-22) ne sont pas dans ce lot.
