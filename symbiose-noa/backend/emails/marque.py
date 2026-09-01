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

# LE VRAI LOGO, quand il est fourni. Le fichier est cherché à côté de ce
# module ; s'il manque, on garde la pastille dessinée ci-dessus — un mail sans
# logo reste lisible, un mail avec un cadre vide fait négligé.
#
# POURQUOI UN PNG ET PAS LE SVG du site (`frontend/public/symbiose-paysage.svg`) :
# aucun client de messagerie ne rend le SVG. Et pourquoi pas une image distante :
# la plupart les bloquent par défaut, et celle-ci vivrait de toute façon derrière
# le VPN, donc inatteignable depuis un téléphone hors réseau.
LOGO_FICHIER = "logo.png"
LOGO_CONTENT_ID = "logo-marque"
# LE LOGO PORTE-T-IL DÉJÀ LE NOM ? Cette question est de la MARQUE, pas du
# socle : ici le logotype est un MOT : « SYMBIOSE PAYSAGE » y est écrit, le répéter à
    # côté ferait doublon.
LOGO_PORTE_LE_NOM = True

MARQUE = {
    "nom": "Symbiose Paysage",
    "couleur": "#1D9E75",          # le bouton : le vert lisible de la charte
    "fond": "#0F1F0E",             # l'en-tête : le vert forêt profond
    "baseline": "#9DB04F",         # la ligne « Assistant IA interne »
    "logo": _LOGO,
    "expediteur_defaut": "Symbiose Paysage <contact@symbiose-paysage.fr>",
}


def logo_image():
    """Les octets du vrai logo, ou None. Ne lève jamais.

    Rendre None n'est pas une panne : le gabarit retombe sur la pastille
    dessinée en HTML, qui ne dépend d'aucun fichier.
    """
    import pathlib as _p

    chemin = _p.Path(__file__).with_name(LOGO_FICHIER)
    try:
        if chemin.exists() and chemin.stat().st_size > 0:
            return {"content_id": LOGO_CONTENT_ID, "nom": LOGO_FICHIER,
                    "mime": "image/png", "octets": chemin.read_bytes()}
    except OSError:
        pass
    return None
