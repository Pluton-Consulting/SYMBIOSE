# Google Drive — mode d'emploi

Ce texte n'est **pas** injecté dans le prompt : il se charge par l'action
`mode_emploi` avec `outil: "drive"`. C'est ce qui permet d'y écrire tout ce qui
serait trop long pour être payé à chaque tour, y compris aux tours qui n'ouvrent
aucun fichier.

## Le vocabulaire de la maison

**Le Drive**, **le cloud**, **Google**, **le partage**, **le serveur** désignent
tous la même chose chez Symbiose Paysage. Personne ne dit « Google Drive » en
entier. Quand quelqu'un demande « ce qu'il y a sur le Drive », c'est `drive_apercu`.

## Ce que le Drive n'est pas

La **mémoire d'entreprise** contient le *contenu* des documents du Drive, ingéré
par la synchronisation : on y cherche une phrase, un montant, une clause. Le
Drive lui-même répond à des questions de *structure* — combien de dossiers, que
contient celui-ci, ouvre-moi tel fichier.

Une recherche documentaire infructueuse ne prouve donc pas qu'un fichier est
absent du Drive, et un fichier présent sur le Drive n'est pas forcément
consultable en mémoire : la synchronisation ne lit ni les images, ni les `.docx`,
ni les PDF scannés sans texte.

## Les quatre gestes

| Action | Quand |
|---|---|
| `drive_apercu` | « combien », « qu'est-ce qu'il y a dans », « c'est gros ? » |
| `drive_arborescence` | voir l'organisation sur plusieurs niveaux |
| `drive_ouvrir` | lire UN fichier dont on connaît le nom |
| `drive_lire_lot` | lire PLUSIEURS fichiers d'un même genre (5 au plus) |

## Le périmètre, et pourquoi il compte

L'assistant ne voit que les dossiers déclarés dans `GOOGLE_DRIVE_PERIMETRES`,
et seulement ceux dont le niveau d'accès est visible par le rôle qui demande.

Un dossier en `direction_only` **n'existe pas** pour un commercial : ni son
contenu, ni son nom, ni le fait qu'il existe. Le filtrage se fait avant le
listage, pas à l'affichage — masquer après coup laisserait fuiter les noms, et
un dossier nommé « Rupture conventionnelle Untel » en dit déjà trop.

Quand aucun dossier n'est ouvert, l'outil lève un refus explicite. **Ce n'est pas
un Drive vide** : répondre « 0 dossier » serait faux et se répéterait de bouche
en bouche.

## Les limites, chiffrées

- **200 entrées** lues par dossier. Au-delà, le résultat porte `tronque: true`
  et une note : un compte partiel ne doit jamais être présenté comme exact.
- **3 niveaux** de profondeur au maximum, **40 dossiers** parcourus au total.
  Un dossier atteint à la limite est marqué `explore: false` — son contenu est
  *inconnu*, pas vide.
- **5 fichiers** par lecture en lot. Le résultat indique combien de fichiers
  correspondaient réellement : « j'ai lu 5 fichiers » sur 40 correspondances
  n'est pas une réponse à « lis les factures de juillet ».
- **20 000 caractères** par fichier ouvert, 6 000 en lecture de lot.

## Ce qui se lit et ce qui ne se lit pas

Se lit : Google Docs, Sheets et Slides (exportés en texte), PDF avec couche
texte, `.txt`, `.md`, `.csv`.

Ne se lit pas : `.docx`, `.xlsx` propriétaires, images, PDF scannés sans OCR.
Le fichier est alors rendu avec une note disant qu'il existe mais que son
contenu n'a pas pu être extrait — ce qui n'est pas la même chose qu'un fichier
introuvable.

## Pannes connues

**« Aucun fichier nommé X »** — la recherche porte sur le nom, dans les dossiers
ouverts, sans descendre dans les sous-dossiers. Un fichier rangé deux niveaux
plus bas ne sera pas trouvé : passer par `drive_arborescence` pour situer le
dossier, puis rouvrir avec le bon `dossier`.

**Un compte qui semble faux** — vérifier `tronque`. Le Drive pagine, et un
dossier de plusieurs milliers d'entrées ne rend que les premières.

**Un fichier visible dans le navigateur mais introuvable ici** — il est
probablement hors des périmètres déclarés, ou dans un Drive partagé auquel le
compte de synchronisation n'a pas été ajouté comme membre.

**Rien ne répond** — le jeton OAuth a peut-être expiré. Si l'écran de
consentement Google est resté « en test », le jeton meurt tous les 7 jours ;
il faut le repasser en « interne » ou « en production ».
