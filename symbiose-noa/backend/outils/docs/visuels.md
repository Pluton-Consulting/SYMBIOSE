# Visuels paysagers (rendus d'aménagement)

Mode d'emploi complet. Les deux actions sont volontairement SÉPARÉES : ce n'est
pas une chaîne à composer, et c'est la seule paire du catalogue dans ce cas.

## Pourquoi deux temps

`preparer_visuel` est **gratuit** et rejouable : il transforme la demande en un
brief précis (sujet, contraintes, matériaux, saison, format) qu'on peut relire,
corriger, refaire autant de fois qu'il faut.

`generer_visuel` est **facturé** à chaque appel, et passe par une validation
humaine. On ne l'appelle jamais pour « essayer » : itérer se fait sur le brief,
pas sur la génération.

Les réunir en une fonction reviendrait à payer un tirage à chaque reformulation.

## Ce que produit la génération

Une **illustration d'ambiance**, pas une simulation du terrain réel : les
proportions, les végétaux et les matériaux sont plausibles, pas mesurés. Elle
sert à faire ressentir une intention d'aménagement à un client, jamais à
remplacer un plan, un métré ou une vue d'implantation.

## Les formats

`16:9` (présentation), `1:1` (réseaux, vignettes), `9:16` (story, mobile).
La résolution standard suffit pour un écran ; la haute résolution ne se
demande que pour l'impression.

## En cas de panne

La génération passe par l'API Google (Nano Banana) avec la clé déjà en place
pour la mémoire et l'analyse d'images. Une clé absente rend une erreur
d'authentification ; un refus de quota dit sa cause — et s'il parle de « palier
gratuit », c'est que la facturation n'est pas activée sur le projet de cette
clé : recharger des crédits ailleurs n'y changera rien. Le brief, lui, n'est
jamais perdu.

## Retoucher une photo plutôt que partir d'une description

Envoyez la photo du terrain : elle est analysée, puis enregistrée sous une
référence que l'assistant vous rappelle. Dites ensuite ce que vous voulez
changer — « remplace la pelouse par une terrasse en bois », « ajoute une
pergola à droite ». La même maison, le même angle, la même lumière sont
conservés ; seuls les points demandés changent. Cela reste une illustration
d'intention : ni un plan, ni une garantie de rendu après travaux.
