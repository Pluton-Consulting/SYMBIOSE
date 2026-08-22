"""
LA MARQUE — Symbiose Paysage.

LE SEUL fichier des mails qui diffère d'un client à l'autre. Quatre valeurs :
le nom, la couleur d'accent (le bouton), le fond de l'en-tête, et le logo.
Dupliquer le produit pour un nouveau client, c'est réécrire ce fichier — et
rien d'autre dans `emails/`.

LE LOGO EST DESSINÉ EN HTML, pas en SVG ni en image : les clients de messagerie
n'affichent pas le SVG, et une image distante est bloquée par défaut chez la
plupart — le destinataire verrait un cadre vide à la place de la marque. Le
logotype complet étant un mot, on en garde ici la pastille : le vert forêt et
l'olive de la charte, qui suffisent à faire reconnaître la marque à côté du nom
écrit en toutes lettres.

L'en-tête disait « PLUTON » et la ligne du dessous « Symbiose Paysage » : le
destinataire lisait le nom de l'agence, pas celui de son propre outil. C'est le
client qui est nommé, ici comme chez son jumeau.
"""

_LOGO = """<table cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="background:#9DB04F;width:36px;height:36px;border-radius:9px;text-align:center;vertical-align:middle">
                        <span style="color:#182B16;font-size:16px;font-weight:800;letter-spacing:-0.5px">S</span>
                      </td>
                    </tr>
                  </table>"""

MARQUE = {
    "nom": "Symbiose Paysage",
    "couleur": "#1D9E75",          # le bouton : le vert lisible de la charte
    "fond": "#0F1F0E",             # l'en-tête : le vert forêt profond
    "baseline": "#9DB04F",         # la ligne « Assistant IA interne »
    "logo": _LOGO,
    "expediteur_defaut": "Symbiose Paysage <contact@symbiose-paysage.fr>",
}
