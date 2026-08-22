"""
Seed du CATALOGUE DE SKILLS génériques — Symbiose Paysage.

Objectif : « roder les agents » en dotant Agent 1 (commercial/administratif) et
Agent 2 (conception/visuels/production) d'un catalogue de capacités métier, au
format attendu par le système (`skills.code` = Python exposant `run(data)->dict`,
statut 'draft' → à valider par la direction, cf. gouvernance du brief §15).

Ces skills sont des SQUELETTES génériques : ils documentent entrées/sorties et ne
renvoient jamais de valeur inventée (champs manquants => "[À COMPLÉTER]", conforme
au brief §5). La logique métier réelle est à implémenter progressivement (ou générée
par l'Agent 3), puis validée humainement.

Idempotent : réexécutable sans doublon (ON CONFLICT (name) DO NOTHING).
Lancement : docker compose exec backend sh -c "PYTHONPATH=. python scripts/seed_skills_catalogue.py"
"""
import asyncio

from database.connection import init_db, get_db


# ── Générateur de squelette de skill (DRY) ────────────────────────────────
def scaffold(name: str, requis: list[str], resultat: list[str]) -> str:
    resultat_lines = "\n".join(f'            {k!r}: "[À COMPLÉTER]",' for k in resultat)
    return (
        "def run(data: dict) -> dict:\n"
        f'    """Skill Symbiose « {name} » : squelette générique.\n'
        f"    Entrées attendues : {requis}.\n"
        '    Règle: ne JAMAIS inventer. Toute donnée absente => "[À COMPLÉTER]".\n'
        '    La logique métier réelle est décrite dans prompt_template."""\n'
        f"    requis = {requis!r}\n"
        "    manquants = [k for k in requis if not data.get(k)]\n"
        "    return {\n"
        f'        "skill": {name!r},\n'
        '        "status": "a_completer" if manquants else "pret",\n'
        '        "champs_manquants": manquants,\n'
        "        \"resultat\": {\n"
        f"{resultat_lines}\n"
        "        },\n"
        '        "note": "Squelette générique : implémenter la logique métier (voir prompt_template).",\n'
        "    }\n"
    )


# ── Catalogue ─────────────────────────────────────────────────────────────
# Skills NATIFS (exécutés dans le backend — voir mail/skills.py).
NATIFS = [
    ("triage_email_entrant",
     "Classe et priorise un message reçu (catégorie, urgence, action suggérée). N'exécute aucune action."),
    ("redaction_email",
     "Rédige un BROUILLON de message dans le style de l'expéditeur, pour 11 types "
     "(réponse, relance devis, relance impayé, envoi de devis, réclamation, information "
     "chantier, confirmation de rendez-vous, demande d'informations, remerciement, refus, "
     "interne). N'envoie jamais."),
    ("resume_fil_email",
     "Résume un échange de mails et en extrait les demandes, engagements et points en attente."),
    ("profil_style_email",
     "(Re)calcule le profil de style rédactionnel d'une boîte à partir de ses messages envoyés."),
]

# (name, agent, category, description, requis[], resultat[], prompt_template)
CATALOGUE = [
    # ===================== AGENT 1 — Commercial / Administratif =====================
    ("recherche_dossier_client", "agent1", "commercial",
     "Retrouve un client et synthétise son dossier (coordonnées, historique, dossiers liés).",
     ["nom_client"], ["client", "coordonnees", "dossiers_lies", "dernier_contact"],
     "Retrouve le client demandé dans la mémoire d'entreprise (RAG source_type='client'). "
     "Restitue une fiche synthétique. N'invente aucune coordonnée ni montant : marque [À COMPLÉTER]."),

    ("historique_devis_client", "agent1", "commercial",
     "Liste et résume les devis d'un client (dates, montants, statuts).",
     ["nom_client"], ["client", "devis", "total_signes", "en_attente"],
     "Récupère les devis liés au client (source_type='devis'). Résume date, montant HT, statut. "
     "Ne calcule pas de total si des montants manquent : [À COMPLÉTER]."),

    ("historique_chantiers_client", "agent1", "commercial",
     "Liste les chantiers réalisés pour un client.",
     ["nom_client"], ["client", "chantiers", "types_travaux"],
     "Récupère les chantiers du client (source_type='chantier'). Restitue lieu, type, année."),

    ("recherche_chantier_similaire", "agent1", "commercial",
     "Trouve des chantiers similaires par lieu et/ou type de travaux.",
     ["critere"], ["chantiers_similaires", "criteres_matches"],
     "Recherche sémantique RAG sur les chantiers (ex: 'terrasse bois à Arcachon'). "
     "Remonte les dossiers pertinents même sans correspondance exacte des termes."),

    ("recherche_info_administrative", "agent1", "administratif",
     "Retrouve un document ou une information administrative (assurance, Kbis, attestation…).",
     ["type_document"], ["document", "reference", "date_validite"],
     "Recherche dans les documents administratifs (source_type='document_admin'). "
     "Ne jamais deviner une date de validité : [À COMPLÉTER] si absente."),

    ("triage_email_entrant", "agent1", "administratif",
     "Classe et priorise un email entrant (catégorie, urgence, action suggérée).",
     ["objet", "corps"], ["categorie", "priorite", "client_detecte", "action_suggeree"],
     "Analyse l'email et classe-le (devis / SAV / administratif / commercial / autre) avec un niveau "
     "de priorité. N'exécute AUCUNE action : propose seulement."),

    ("redaction_reponse_email", "agent1", "administratif",
     "Rédige un BROUILLON de réponse à un email (validation humaine obligatoire avant envoi).",
     ["objet", "corps"], ["brouillon_reponse", "ton", "elements_a_verifier"],
     "Rédige un brouillon professionnel en français. ⚠ VALIDATION HUMAINE OBLIGATOIRE avant tout envoi. "
     "N'invente ni prix ni engagement : [À COMPLÉTER]."),

    ("relance_client", "agent1", "commercial",
     "Prépare une relance client (devis en attente, dossier sans réponse).",
     ["nom_client", "motif"], ["brouillon_relance", "contexte", "elements_a_verifier"],
     "Prépare un message de relance courtois et contextualisé. ⚠ Validation humaine avant envoi."),

    ("preparation_elements_devis", "agent1", "commercial",
     "Rassemble les éléments nécessaires à la préparation d'un devis.",
     ["nom_client", "objet_travaux"], ["client", "historique_pertinent", "postes_pressentis", "manque"],
     "Agrège client + historiques + méthodes internes pour préparer un devis. "
     "Ne CHIFFRE pas : prépare seulement. Le chiffrage final est humain."),

    ("suivi_dossier_client", "agent1", "commercial",
     "Donne l'état d'avancement d'un dossier client.",
     ["nom_client"], ["etape_actuelle", "prochaines_actions", "documents_manquants"],
     "Synthétise où en est le dossier (devis, signature, chantier, facturation) d'après la mémoire."),

    ("synthese_echanges_client", "agent1", "commercial",
     "Résume l'historique des échanges avec un client.",
     ["nom_client"], ["synthese", "points_ouverts", "dernier_echange"],
     "Produit une synthèse chronologique des échanges. Reste factuel, cite les sources internes."),

    ("recherche_documentaire", "agent1", "memoire",
     "Recherche transverse dans la mémoire d'entreprise (tous types de documents).",
     ["requete"], ["resultats", "sources"],
     "Recherche sémantique RAG globale. Restitue les extraits pertinents avec leur source. "
     "Si rien n'est trouvé, le dire clairement et ne jamais inventer."),

    # ===================== AGENT 2 — Conception / Visuels / Production =====================
    ("analyse_plan_pdf", "agent2", "conception",
     "Extrait les informations clés d'un plan PDF (échelle, cotes, zones, légende).",
     ["fichier"], ["echelle", "surfaces_detectees", "zones", "elements_remarquables"],
     "Analyse le plan (Vision). Extrait échelle, cotes et zones. "
     "Signale toute incertitude de lecture ; ne devine pas une cote absente."),

    ("analyse_plan_cadastral", "agent2", "conception",
     "Analyse un plan cadastral (parcelle, surface, limites, riverains).",
     ["fichier"], ["parcelle", "surface_m2", "limites", "contraintes"],
     "Identifie parcelle et surface. N'affirme une surface que si lisible, sinon [À COMPLÉTER]."),

    ("analyse_photo_terrain", "agent2", "conception",
     "Réalise un état des lieux à partir d'une photo de terrain.",
     ["fichier"], ["etat_existant", "elements_vegetaux", "contraintes", "opportunites"],
     "Décris l'existant visible (végétation, revêtements, accès, dénivelé). "
     "⚠ Retire les métadonnées EXIF/GPS des photos avant traitement."),

    ("estimation_surfaces", "agent2", "conception",
     "Calcule les surfaces d'aménagement (terrasse, engazonnement, allées…).",
     ["cotes"], ["surfaces", "hypotheses", "total_m2"],
     "Calcule les surfaces à partir des cotes fournies. Explicite chaque hypothèse. "
     "Si des cotes manquent, ne calcule pas le total : [À COMPLÉTER]."),

    ("recherche_projets_similaires", "agent2", "conception",
     "Recherche des projets/chantiers similaires pour inspiration et référence de chiffrage.",
     ["description_projet"], ["projets_similaires", "postes_recurrents"],
     "Recherche RAG (chantiers + devis) sur des projets comparables. Remonte postes récurrents."),

    ("generation_visuel_paysager", "agent2", "visuels",
     "Génère un visuel paysager (Nano Banana) à partir d'un brief.",
     ["brief"], ["cles_images", "parametres", "variantes"],
     "Livré : `preparer_visuel` assemble le brief, `tester_visuel` itère, `generer_visuel` "
     "produit le tirage final. ⚠ Coût API à l'usage : validation avant le tirage final."),

    ("simulation_avant_apres", "agent2", "visuels",
     "Produit un rendu avant/après à partir d'une photo terrain et d'un projet.",
     ["photo", "projet"], ["url_apres", "description_transformation"],
     "Livré : `modifier_visuel` — la photo est donnée AU modèle, pas décrite, et un "
     "préréglage de fidélité verrouille tout ce qui ne doit pas bouger (bâti, angle, "
     "lumière). ⚠ Validation avant génération."),

    ("variantes_amenagement", "agent2", "conception",
     "Propose plusieurs variantes d'aménagement pour un espace.",
     ["contraintes"], ["variantes", "avantages_inconvenients"],
     "Propose 2 à 3 variantes argumentées (usage, budget indicatif, entretien). "
     "Les budgets restent indicatifs et à valider."),

    ("extraction_postes_travaux", "agent2", "production",
     "Extrait les postes de travaux depuis un plan, une photo ou une description.",
     ["source"], ["postes", "quantites_estimees", "postes_incertains"],
     "Décompose en postes de travaux (terrassement, maçonnerie, plantation…). "
     "Marque les quantités incertaines [À COMPLÉTER] plutôt que d'inventer."),

    ("preparation_liste_taches", "agent2", "production",
     "Prépare une liste de tâches / planning prévisionnel de chantier.",
     ["postes"], ["taches", "sequencement", "prerequis"],
     "Ordonne les tâches en séquence logique avec prérequis. Prévisionnel indicatif."),

    ("base_prechiffrage", "agent2", "production",
     "Prépare une base de PRÉ-DEVIS (jamais un chiffrage final, validation humaine obligatoire).",
     ["postes"], ["lignes_prechiffrage", "hypotheses", "a_valider"],
     "Assemble une base de pré-chiffrage à partir des postes + méthodes internes + prix de référence. "
     "⚠⚠ NE VALIDE JAMAIS un chiffrage : la décision finale et les montants restent 100% humains."),
]


async def main() -> None:
    await init_db()
    async with get_db() as conn:
        # Colonnes d'organisation / gouvernance (idempotent)
        await conn.execute("ALTER TABLE skills ADD COLUMN IF NOT EXISTS agent VARCHAR(20)")
        await conn.execute("ALTER TABLE skills ADD COLUMN IF NOT EXISTS category VARCHAR(50)")
        await conn.execute("ALTER TABLE skills ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true")

        inserted = 0
        for name, agent, category, description, requis, resultat, prompt in CATALOGUE:
            code = scaffold(name, requis, resultat)
            status = await conn.execute(
                """INSERT INTO skills
                       (name, description, code, prompt_template, status, created_by, agent, category)
                   VALUES ($1, $2, $3, $4, 'draft', 'system', $5, $6)
                   ON CONFLICT (name) DO NOTHING""",
                name, description, code, prompt, agent, category,
            )
            if status.endswith(" 1"):
                inserted += 1

        # Skills NATIFS : implémentés dans le backend (mail/skills.py), pas en bac
        # à sable. Ils sont donc directement 'stable' — leur code est livré avec
        # l'application, il n'y a rien à générer ni à valider. Les référencer ici
        # les rend visibles et surtout DÉSACTIVABLES depuis l'interface.
        for name, description in NATIFS:
            status = await conn.execute(
                """INSERT INTO skills
                       (name, description, code, prompt_template, status, created_by, agent, category)
                   VALUES ($1, $2, '', '', 'stable', 'system', 'agent1', 'mail')
                   ON CONFLICT (name) DO UPDATE
                       SET description = EXCLUDED.description, status = 'stable'""",
                name, description,
            )
            if status.endswith(" 1"):
                inserted += 1

        total = await conn.fetchval("SELECT COUNT(*) FROM skills")
        by_agent = await conn.fetch(
            "SELECT agent, category, COUNT(*) n FROM skills GROUP BY agent, category ORDER BY agent, category"
        )

    print(f"Skills insérées cette exécution : {inserted}")
    print(f"Total skills en base : {total}")
    print("Répartition :")
    for r in by_agent:
        print(f"  {r['agent'] or '—':8} / {r['category'] or '—':14} : {r['n']}")


if __name__ == "__main__":
    asyncio.run(main())
