"""Recherche plein texte Drive dans les seuls périmètres autorisés."""
from skills.registre import Declaration
async def chercher(data,user):
    import asyncio
    from skills.outils import _drive,_perimetres,_identite
    from outils.drive import chercher
    motif=str(data.get("motif") or "").strip()
    if not motif:raise ValueError("Précise les mots à rechercher dans le contenu.")
    try:
        r=await asyncio.wait_for(_drive(chercher,motif,perimetres=_perimetres(user),identite=_identite(user),page=data.get("page") or 1,genre="fichiers",dans_contenu=True), timeout=45)
    except asyncio.TimeoutError:
        raise ValueError("La recherche plein texte Drive a dépassé 45 secondes. Le service Google ne répond pas assez vite ; aucun fichier n'a été modifié.")
    r["a_faire"]="Ces fichiers correspondent à l’index plein texte de Google ; ouvre leur contenu avant de citer. Ce résultat ne prouve pas que tous les formats, scans ou pièces sont indexés. Respecte partiel et les pages restantes."
    return r
SKILLS={"drive_chercher_contenu":Declaration(chercher,"Rechercher des mots dans le contenu indexé par Google Drive, avec les droits et les périmètres courants. Ouvrir ensuite les fichiers pertinents ; une correspondance n’est pas une lecture.",requis=["motif"],optionnels=["page"],effet="lecture",libelle="je cherche dans le contenu du Drive")}
