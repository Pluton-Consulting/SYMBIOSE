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

La génération est un service externe (Higgsfield) : une clé absente ou expirée
rend une erreur d'authentification, un délai dépassé signifie que le service
est surchargé : réessayer plus tard, le brief n'est pas perdu.
