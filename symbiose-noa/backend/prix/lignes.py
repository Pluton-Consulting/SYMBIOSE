"""
LIRE LES LIGNES CHIFFRÉES D'UN DEVIS OU D'UNE FACTURE DE LA MAISON — du code, pas un modèle.

Pourquoi ce module existe (17/09, Symbiose) : « récupère le mail de … et fais-moi un
pré-devis » rendait « aucun prix maison », alors que l'entreprise a émis plus de mille
devis. Les fichiers importés (jeux « devis », « facture ») ne portent que des TOTAUX par
affaire : un devis de 30 000 € ne dit rien du prix d'un abattage. Le détail — désignation,
unité, quantité, prix unitaire — n'existe que dans les PDF du classement.

POURQUOI PAS UN MODÈLE. Deux mille PDF à faire lire par un modèle, c'est des heures, des
jetons, et des chiffres recopiés à peu près. Or le logiciel de gestion pose chaque ligne de
la même façon sur la page, et surtout chaque ligne SE VÉRIFIE PAR LE CALCUL :

        quantité × prix unitaire = montant HT      et      montant HT × (1 + TVA) = montant TTC

On lit donc des MOTS POSITIONNÉS (x, y), on les range par rangées, et l'on garde les
rangées dont les nombres de droite tombent juste. Ce qui ne tombe pas juste n'entre pas.
Conséquences voulues :
  * une facture de FOURNISSEUR, un relevé, un bon d'un autre format ne produisent rien —
    un prix d'ACHAT glissé dans les prix de VENTE fausserait toutes les estimations ;
  * un devis SCANNÉ (quatre sur cinq dans le classement : imprimés en image, ou signés
    puis numérisés) peut passer par l'OCR sans risque : un chiffre mal reconnu casse le
    calcul, la ligne est écartée au lieu d'entrer fausse. C'est le calcul qui autorise
    l'OCR ici, alors qu'on le refuserait pour une base de prix sans contrôle.

Les mots viennent de PyMuPDF (PDF texte) ou de tesseract (PDF image) : même forme, même
lecteur. Les fonctions de lecture sont pures — ni réseau, ni base.
"""
from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple, Optional


class Mot(NamedTuple):
    x0: float
    x1: float
    y: float          # haut du mot, en points
    h: float          # hauteur du mot
    texte: str
    gras: bool = False


# Un nombre tel que le logiciel l'écrit : « 2 910.00 », « 27 788,00 », « 1.00 », « -126.60 ».
_NOMBRE = re.compile(r"^-?\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,4})?$|^-?\d+(?:[.,]\d{1,4})?$")
_MILLIERS_DEBUT = re.compile(r"^-?\d{1,3}$")
_MILLIERS_SUITE = re.compile(r"^\d{3}(?:[.,]\d{1,4})?$")

# Ce qui identifie une pièce ÉMISE par la maison. Un document qui ne porte aucune de ces
# mentions n'est pas lu : on ne devine pas la nature d'un PDF à la forme de ses nombres.
_PIECE = re.compile(
    # « Facture n° J2025-156141 » (auto-facturation Jardiniers SAP, 18/09) : le numéro porte un tiret.
    # Sans lui, 275 factures de 2025 se lisaient « J2025 » et n'en faisaient plus qu'UNE au calcul.
    r"\b(devis|facture|avoir|commande|situation)\s*(?:d['’]acompte\s*)?n\s?[°ºo]\s*:?\s*([A-Z]{1,4}\s?\d{3,}(?:-\d{2,})?)",
    re.IGNORECASE)
_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")

# Tolérance du contrôle arithmétique : les montants sont arrondis au centime, et une
# quantité à trois décimales peut déplacer le produit d'un centime ou deux.
_TOLERANCE = 0.06

UNITES = {"forfait", "ft", "fft", "u", "un", "unite", "unité", "unites", "unités", "m2", "m²",
          "ml", "m", "m3", "m³", "h", "heure", "heures", "j", "jour", "jours", "kg", "t",
          "tonne", "tonnes", "l", "litre", "litres", "ens", "ens.", "ensemble", "pce", "pièce",
          "piece", "pièces", "lot", "mois", "an", "passage", "passages", "sac", "sacs"}
MAX_DESIGNATION = 400
MAX_RUBRIQUE = 90
MAX_LIGNES_PAR_PIECE = 400

# Rangées du gabarit : elles ferment une désignation et n'y entrent jamais.
_BRUIT = re.compile(
    r"^(total\b|sous[- ]?total|net à payer|base ht|montant tva|mode de r[èe]glement|"
    r"date d['’]échéance|banque|iban|bic|en cas d['’]acceptation|durée de validité|"
    r"date\s*:.*signature|page\b|suivi par|report\b|à reporter)", re.IGNORECASE)
_ENTETE = re.compile(r"(description|d[ée]signation).*(qt[ée]|pu\b|montant)", re.IGNORECASE)
# Ce qui n'est pas une prestation : un acompte ou une remise n'a pas de « prix ».
_HORS_PRIX = re.compile(r"^\s*(acompte|remise|avoir|déduction|deduction|reprise d['’]acompte)\b",
                        re.IGNORECASE)


def nombre(texte: str) -> Optional[float]:
    """La valeur d'un nombre écrit par le logiciel, ou None si ce n'en est pas un."""
    t = (texte or "").strip().replace("€", "").replace("%", "").strip()
    if not t or not _NOMBRE.match(t):
        return None
    t = t.replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _proche(a: float, b: float) -> bool:
    return abs(a - b) <= max(_TOLERANCE, abs(b) * 0.0006)


def _plat(texte: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


# ── DES MOTS AUX RANGÉES ─────────────────────────────────────────────────────
def rangees(mots: list[Mot]) -> list[list[Mot]]:
    """Les mots d'une page rangés par lignes visuelles, de haut en bas, de gauche à droite."""
    # On compare les MILIEUX, pas les hauts : à l'OCR un « p » et un « t » de la même ligne
    # n'ont pas le même haut, et deux lignes serrées se fondaient en une seule rangée aux
    # mots mélangés (« Fourniture et de miroirs … pose en cm »).
    milieu = lambda m: m.y + (m.h or 8) / 2
    hauteurs = sorted((m.h or 8) for m in mots if m.texte.strip())
    pas = 0.45 * (hauteurs[len(hauteurs) // 2] if hauteurs else 8)
    lignes: list[list[Mot]] = []
    centres: list[float] = []
    for m in sorted(mots, key=milieu):
        if not m.texte.strip():
            continue
        if lignes and abs(centres[-1] - milieu(m)) <= max(2.0, pas):
            lignes[-1].append(m)
            centres[-1] = sum(milieu(x) for x in lignes[-1]) / len(lignes[-1])
        else:
            lignes.append([m])
            centres.append(milieu(m))
    return [sorted(l, key=lambda m: m.x0) for l in lignes]


def _recoller_milliers(rangee: list[Mot]) -> list[Mot]:
    """« 27 » « 788.00 » → « 27 788.00 » quand l'espace est celui des milliers, pas d'une colonne."""
    sortie: list[Mot] = []
    for m in rangee:
        p = sortie[-1] if sortie else None
        if (p is not None and "." not in p.texte and "," not in p.texte
                and _MILLIERS_DEBUT.match(p.texte.split(" ")[-1])
                and _MILLIERS_SUITE.match(m.texte)
                and 0 <= m.x0 - p.x1 <= 0.75 * (m.h or 8)):
            sortie[-1] = Mot(p.x0, m.x1, p.y, p.h, f"{p.texte} {m.texte}")
        else:
            sortie.append(m)
    return sortie


# LA VERSION DU LECTEUR. La collecte la range avec chaque pièce : quand le lecteur apprend un
# gabarit de plus, les pièces lues par une version plus ancienne sont rouvertes d'elles-mêmes.
VERSION = 5     # 18/09 : numéro à tiret (J2025-156141), client « Prestation effectuée pour »


def _gabarit_tva_au_milieu(mots: list[Mot]) -> Optional[dict]:
    """Le second gabarit de la maison : « DÉSIGNATION · QTE · UNITÉ · TVA · P.U. HT · TOTAL HT ».
    La rangée finit par « 20,00 % · 878,09 € · 878,09 € » et la quantité précède, avec ou sans
    unité entre les deux. Le « % » fait la structure, quantité × PU = total fait la preuve."""
    if len(mots) < 4 or "%" not in mots[-3].texte:
        return None
    tva, pu, ht = (nombre(m.texte) for m in mots[-3:])
    if tva is None or pu is None or ht is None or not (0 <= tva <= 33):
        return None
    for recul in (4, 5):                      # la quantité : juste avant la TVA, ou avant l'unité
        if len(mots) < recul:
            break
        q = nombre(mots[-recul].texte)
        if q is not None and q > 0 and _proche(q * pu, ht):
            avant = mots[:-recul] + (mots[-4:-3] if recul == 5 else [])
            return {"quantite": q, "pu_ht": pu, "montant_ht": ht, "tva": tva, "avant": avant,
                    "x_nombres": mots[-recul].x0}
    return None


def _ligne_chiffree(rangee: list[Mot]) -> Optional[dict]:
    """Si la rangée porte une ligne de prix QUI TOMBE JUSTE, ses valeurs et ce qui la précède."""
    mots = _recoller_milliers(rangee)
    autre = _gabarit_tva_au_milieu(mots)
    if autre:
        return autre
    # La suite de nombres qui ferme la rangée : Qté, PU HT, Montant HT, [TVA], [Montant TTC].
    k = len(mots)
    while k > 0 and nombre(mots[k - 1].texte) is not None:
        k -= 1
    valeurs = [nombre(m.texte) for m in mots[k:]]
    # LE GABARIT DES FACTURES : « Description · Qté · UNITÉS · PU HT · Montant HT · TVA · TTC ».
    # L'unité est ENTRE la quantité et le prix : la suite de nombres de droite commence au PU,
    # et la quantité attend de l'autre côté de l'unité. (21 factures sur 40 sans ligne, 17/09.)
    if 2 <= len(valeurs) <= 4 and k >= 2 and len(mots[k - 1].texte) <= 10:
        q = nombre(mots[k - 2].texte)
        pu, ht = valeurs[0], valeurs[1]
        tva = valeurs[2] if len(valeurs) >= 3 else None
        if (q is not None and q > 0 and _proche(q * pu, ht) and (tva is None or 0 <= tva <= 33)
                and (len(valeurs) < 4 or _proche(ht * (1 + tva / 100), valeurs[3]))):
            return {"quantite": q, "pu_ht": pu, "montant_ht": ht, "tva": tva, "avant": mots[:k - 2],
                    "unite": mots[k - 1].texte, "x_nombres": mots[k - 2].x0}
    # Une désignation peut finir par un nombre (« … de 7.40 ») : on essaie les cinq, puis
    # les quatre, puis les trois derniers nombres, et l'on garde la lecture qui tombe juste.
    # AVEC UNE REMISE : Qté · PU · Remise % · Montant · TVA · TTC. Le prix qui compte est le NET
    # (montant ÷ quantité) : c'est celui que le client a payé, pas celui du tarif.
    if len(valeurs) >= 6:
        q, pu, remise, ht, tva, ttc = valeurs[-6:]
        if (q > 0 and 0 < remise < 100 and 0 <= tva <= 33 and _proche(q * pu * (1 - remise / 100), ht)
                and _proche(ht * (1 + tva / 100), ttc)):
            return {"quantite": q, "pu_ht": round(ht / q, 4), "montant_ht": ht, "tva": tva,
                    "avant": mots[:len(mots) - 6], "x_nombres": mots[len(mots) - 6].x0,
                    "remise": remise}
    for taille in (5, 4, 3):
        if len(valeurs) < taille:
            continue
        v = valeurs[-taille:]
        q, pu, ht = v[0], v[1], v[2]
        if q is None or q <= 0 or not _proche(q * pu, ht):
            continue
        tva = v[3] if taille >= 4 else None
        if tva is not None and not (0 <= tva <= 33):
            continue
        if taille == 5 and not _proche(ht * (1 + tva / 100), v[4]):
            continue
        avant = mots[:len(mots) - taille]
        return {"quantite": q, "pu_ht": pu, "montant_ht": ht, "tva": tva, "avant": avant,
                "x_nombres": mots[len(mots) - taille].x0}
    return None


def _unite_et_texte(avant: list[Mot]) -> tuple[str, list[Mot]]:
    """L'unité est le dernier mot avant les nombres, s'il en a l'air ; le reste décrit."""
    if not avant:
        return "", []
    dernier = avant[-1]
    ecart = dernier.x0 - avant[-2].x1 if len(avant) > 1 else 99
    if _plat(dernier.texte) in UNITES or (len(dernier.texte) <= 10 and ecart > 15):
        return dernier.texte, avant[:-1]
    return "", avant


def _texte(mots: list[Mot]) -> str:
    return " ".join(m.texte for m in mots).strip()


def _a_l_air_d_un_titre(rangee: list[Mot]) -> bool:
    """Un titre de rubrique est court, et il est en gras ou en capitales. Tout le reste —
    fin d'une désignation coupée par un blanc, mention en bas de tableau — titrait à tort
    la ligne suivante (« [TVA] Taille du 04-06-26 »)."""
    t = _texte(rangee)
    lettres = [c for c in t if c.isalpha()]
    if not (4 <= len(t) <= MAX_RUBRIQUE) or len(lettres) < 4:
        return False
    capitales = sum(1 for c in lettres if c.isupper()) / len(lettres)
    return capitales >= 0.7 or all(m.gras for m in rangee)


def lire_page(mots: list[Mot]) -> list[dict]:
    """Les lignes chiffrées d'UNE page."""
    R = rangees(mots)
    lues = [_ligne_chiffree(r) for r in R]
    y_entete = next((r[0].y for r in R if _ENTETE.search(_texte(r))), None)
    resultat: list[dict] = []
    rubrique = ""
    i = 0
    while i < len(R) and len(resultat) < MAX_LIGNES_PAR_PIECE:
        ligne = lues[i]
        if not ligne:
            t = _texte(R[i])
            # Une rangée de texte seule, SOUS l'en-tête du tableau, titre ce qui suit. Au-dessus
            # de l'en-tête vivent le nom et l'adresse du client : ils n'entrent nulle part.
            if (y_entete is not None and R[i][0].y > y_entete + 4 and not _BRUIT.match(t)
                    and not _ENTETE.search(t) and _a_l_air_d_un_titre(R[i])):
                rubrique = t
            i += 1
            continue
        unite, debut = ((ligne["unite"], ligne["avant"]) if "unite" in ligne
                        else _unite_et_texte(ligne["avant"]))
        morceaux = [_texte(debut)]
        x_desc = debut[0].x0 if debut else 0
        hauteur = (R[i][0].h or 9)
        y_prec = R[i][0].y
        j = i + 1
        # La suite de la désignation : des rangées de texte SERRÉES sous la première, dans la
        # colonne de gauche. Un blanc, une autre ligne chiffrée ou le gabarit la ferment.
        while j < len(R) and not lues[j]:
            r = R[j]
            t = _texte(r)
            if (r[0].y - y_prec > 2.1 * hauteur or _BRUIT.match(t) or _ENTETE.search(t)
                    or r[-1].x1 > ligne["x_nombres"] or r[0].x0 < x_desc - 6):
                break
            morceaux.append(t)
            y_prec = r[0].y
            j += 1
        designation = " ".join(" ".join(morceaux).split())
        # « 2 Fourniture et pose… » : le numéro d'ordre n'est pas la désignation.
        designation = re.sub(r"^\d{1,3}(?:\.\d{1,3})*\s+(?=\D)", "", designation)[:MAX_DESIGNATION]
        if len(designation) >= 4 and ligne["pu_ht"] > 0 and not _HORS_PRIX.match(designation):
            resultat.append({"designation": designation, "rubrique": rubrique, "unite": unite,
                             "quantite": ligne["quantite"], "pu_ht": ligne["pu_ht"],
                             "montant_ht": ligne["montant_ht"], "tva": ligne["tva"]})
        i = j
    return resultat


# ── CE QUE LA PIÈCE DIT D'ELLE-MÊME ──────────────────────────────────────────
def nature_et_numero(texte: str) -> tuple[Optional[str], Optional[str]]:
    """(« devis » | « facture » | …, numéro) — ou (None, None) si la pièce n'est pas de la maison."""
    m = _PIECE.search(texte or "")
    if not m:
        return None, None
    return _plat(m.group(1)), re.sub(r"\s+", "", m.group(2)).upper()


def date_de_la_piece(lignes: list[str]) -> Optional[date]:
    """La date de la pièce : celle d'une rangée « Date », sinon la première date écrite."""
    def lire(t: str) -> Optional[date]:
        for m in _DATE.finditer(t):
            j, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
            a += 2000 if a < 100 else 0
            try:
                if 2000 <= a <= 2100:
                    return date(a, mo, j)
            except ValueError:
                continue
        return None
    for t in lignes:
        if re.match(r"^\s*date\b", t, re.IGNORECASE) and "échéance" not in t.lower() and "validité" not in t.lower():
            d = lire(t)
            if d:
                return d
    for t in lignes:
        if "échéance" in t.lower() or "validité" in t.lower():
            continue
        d = lire(t)
        if d:
            return d
    return None


def titre_de_la_piece(lignes: list[str]) -> str:
    """L'intitulé de l'affaire : la rangée qui suit « Devis N° … »."""
    for k, t in enumerate(lignes[:-1]):
        if _PIECE.search(t):
            reste = _PIECE.sub("", t).strip(" :-")
            suivant = reste if len(reste) > 6 else lignes[k + 1]
            if nombre(suivant) is None and not _BRUIT.match(suivant) and not _ENTETE.search(suivant):
                return suivant[:160]
    return ""


# LE CLIENT DE LA PIÈCE (17/09). Le logiciel l'écrit toujours au même endroit : la première
# rangée du bloc d'adresse, « [Code client : 90DUPON] … Adresse Chantier : M. DUPONT Jean ».
# Sans lui, ni chiffre d'affaires par client, ni « dernière prestation réalisée chez lui ».
# Le CODE client, quand il est écrit, regroupe mieux que le nom (« Mme DUPONT », « DUPONT Anne »).
_CODE_CLIENT = re.compile(r"code\s*client\s*:?\s*([A-Z0-9][A-Z0-9_\-]{2,19})", re.IGNORECASE)
_NOM_CLIENT = re.compile(r"adresse\s*(?:de\s*)?(?:chantier|livraison|facturation)\s*:\s*(.+)$", re.IGNORECASE)
# Auto-facturation Jardiniers SAP : le client est écrit SOUS « Prestation effectuée pour : ».
_PRESTATION_POUR = re.compile(r"prestation\s+effectu[ée]e?\s+pour\s*:\s*(.*)$", re.IGNORECASE)
MAX_CLIENT = 80


def client_de_la_piece(lignes: list[str]) -> tuple[str, str]:
    """(nom du client, code client) — chacun vide s'il n'est pas écrit. Jamais deviné."""
    nom, code = "", ""
    for t in lignes[:40]:
        if not code:
            m = _CODE_CLIENT.search(t)
            if m:
                code = m.group(1).upper()
        if not nom:
            m = _NOM_CLIENT.search(t)
            if m:
                # À l'OCR la rangée se prolonge parfois par l'étiquette voisine (« … Email »).
                brut = re.split(r"\s+(?:email|e-mail|mobile|t[ée]l)\b", m.group(1), flags=re.IGNORECASE)[0]
                nom = " ".join(brut.split())[:MAX_CLIENT].strip(" ,;:-")
        if nom and code:
            break
    if not nom:
        for i, t in enumerate(lignes[:60]):
            m = _PRESTATION_POUR.search(t)
            if m:
                suite = (m.group(1) or "").strip() or (lignes[i + 1].strip() if i + 1 < len(lignes) else "")
                nom = " ".join(suite.split())[:MAX_CLIENT].strip(" ,;:-")
                break
    return nom, code


def lire_pages(pages: list[list[Mot]]) -> Optional[dict]:
    """Une pièce de la maison et ses lignes, depuis les mots de ses pages — ou None."""
    textes = [[_texte(r) for r in rangees(p)] for p in pages]
    a_plat = [t for page in textes for t in page]
    nature, numero = nature_et_numero("\n".join(a_plat))
    if not nature:
        return None
    lignes: list[dict] = []
    for p in pages:
        lignes.extend(lire_page(p))
    # « Total HT : 776.92 € » vit au milieu d'une rangée du pied de page (mode de règlement à
    # gauche, totaux à droite). Il sert de CONTRÔLE : la somme des lignes lues doit le retrouver.
    total = None
    for t in a_plat:
        m = re.search(r"total\s*h\.?\s?t\.?\s*:?\s*(-?\d[\d \u00a0\u202f]*[.,]\d{2})", t, re.IGNORECASE)
        if m and nombre(m.group(1).strip()) is not None:
            total = nombre(m.group(1).strip())
    client, code_client = client_de_la_piece(textes[0] if textes else [])
    return {"nature": nature, "numero": numero, "date": date_de_la_piece(a_plat),
            "titre": titre_de_la_piece(a_plat), "total_ht": total,
            "client": client, "code_client": code_client,
            "lignes": lignes[:MAX_LIGNES_PAR_PIECE]}


# ── D'UN PDF AUX MOTS ────────────────────────────────────────────────────────
MAX_PAGES = 30
OCR_DPI = 200


def mots_du_pdf(octets: bytes) -> tuple[list[list[Mot]], bool]:
    """(mots par page, a_du_texte). PyMuPDF rend des lignes déjà assemblées : « 27 788.00 »
    arrive en un morceau, ce qui épargne le recollage des milliers."""
    import pymupdf
    pages: list[list[Mot]] = []
    caracteres = 0
    with pymupdf.open(stream=octets, filetype="pdf") as doc:
        for page in list(doc)[:MAX_PAGES]:
            mots: list[Mot] = []
            for bloc in page.get_text("dict").get("blocks", []):
                for ligne in bloc.get("lines", []):
                    for span in ligne.get("spans", []):
                        t = (span.get("text") or "").strip()
                        if not t:
                            continue
                        x0, y0, x1, y1 = span["bbox"]
                        caracteres += len(t)
                        # Un span « 1   Fourniture et pose » se découpe : le lecteur raisonne par mots.
                        gras = bool(span.get("flags", 0) & 16) or "bold" in str(span.get("font", "")).lower()
                        if nombre(t) is not None:
                            mots.append(Mot(x0, x1, y0, y1 - y0, t, gras))
                            continue
                        morceaux = t.split()
                        pas = (x1 - x0) / max(1, len(t))
                        curseur = x0
                        for mc in morceaux:
                            debut = curseur
                            fin = debut + pas * len(mc)
                            mots.append(Mot(debut, fin, y0, y1 - y0, mc, gras))
                            curseur = fin + pas
            pages.append(mots)
    return pages, caracteres >= 80


def mots_par_ocr(octets: bytes, max_pages: int = 6) -> list[list[Mot]]:
    """Les mots d'un PDF IMAGE, par tesseract. Passe par la porte commune de l'OCR
    (`ingestion.parsers`) : deux lectures de front au plus sur tout le serveur."""
    import pymupdf
    import pytesseract
    from PIL import Image
    from ingestion import parsers
    pages: list[list[Mot]] = []
    echelle = 72.0 / OCR_DPI
    with pymupdf.open(stream=octets, filetype="pdf") as doc:
        for page in list(doc)[:max_pages]:
            pix = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY)
            image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            while not parsers._OCR_PORTE.acquire(timeout=1):
                pass
            try:
                d = pytesseract.image_to_data(image, lang="fra", config="--psm 6",
                                              timeout=parsers.OCR_DELAI_PAGE_S,
                                              output_type=pytesseract.Output.DICT)
            except RuntimeError:
                d = {"text": []}
            finally:
                parsers._OCR_PORTE.release()
            mots: list[Mot] = []
            for k, t in enumerate(d.get("text") or []):
                # Les filets du tableau sortent en « | » collés aux mots : « |Forfait », « 2|Jardinières ».
                t = (t or "").replace("|", " ").strip(" []{}_—~`")
                if not t or float(d["conf"][k]) < 30:
                    continue
                x0 = d["left"][k] * echelle
                mots.append(Mot(x0, x0 + d["width"][k] * echelle, d["top"][k] * echelle,
                                d["height"][k] * echelle, t))
            pages.append(mots)
    return pages


def lire_piece(octets: bytes, ocr: bool = True) -> Optional[dict]:
    """Une pièce de la maison et ses lignes. `methode` dit d'où viennent les mots."""
    pages, a_du_texte = mots_du_pdf(octets)
    if a_du_texte:
        piece = lire_pages(pages)
        if piece is not None:
            piece["methode"] = "texte"
        return piece
    if not ocr:
        return None
    piece = lire_pages(mots_par_ocr(octets))
    if piece is not None:
        piece["methode"] = "ocr"
    return piece
