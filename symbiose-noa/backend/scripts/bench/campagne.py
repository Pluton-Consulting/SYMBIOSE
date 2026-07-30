#!/usr/bin/env python
"""
Banc de campagne — pose la banque de questions à l'assistant et NOTE les réponses.

À quoi ça sert, précisément : `test_e2e.py` répond à « est-ce que ça marche ? ».
Celui-ci répond à « est-ce que ça répond BIEN, et est-ce que ça s'améliore ? ».
La différence tient au fait que la banque de questions est figée et versionnée :
un run se compare au précédent, question par question, et les REGRESSIONS
ressortent d'elles-mêmes.

Deux niveaux de notation, volontairement séparés :

  * les contrôles DURS (`dur`) ne consultent aucun modèle. Latence, chiffres
    présents, jetons de masquage qui fuient, composant attendu, recherche
    déclenchée ou non. Ils sont fiables et reproductibles : c'est sur eux que
    repose le verdict.
  * le JUGE (`juge`) est un modèle à qui l'on demande si la réponse satisfait un
    critère écrit à l'avance. Il attrape ce qu'aucune règle ne sait voir (le
    hors-sujet, le ton, l'invention). Il se trompe parfois : ses verdicts sont
    donc rapportés à part, jamais fondus dans le score dur.

Usage, dans le conteneur :
    docker compose -f docker-compose.yml -f docker-compose.prod.yml \
      exec -T backend sh -c "PYTHONPATH=. python scripts/bench/campagne.py"

Options :
    --categorie X   ne joue qu'une catégorie (conversation, rag, chiffres...)
    --limite N      s'arrête après N questions
    --pause S       secondes entre deux questions (défaut 2 ; monter si la
                    cascade gratuite renvoie des 429)
    --sans-juge     contrôles durs seulement : aucun appel de notation
    --garder        conserve le document de test en base
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, ".")

ICI = os.path.dirname(os.path.abspath(__file__))
RAPPORTS = os.path.join(ICI, "rapports")

VERT, ROUGE, JAUNE, GRIS, RAZ = "\033[92m", "\033[91m", "\033[93m", "\033[90m", "\033[0m"

MARQUEUR = "ZZTEST"
SOURCE_TEST = "zztest_chantier"

# Le même document de référence que le banc e2e : on connaît son contenu par
# cœur, donc on peut juger si la réponse s'y appuie vraiment.
DOC_TEST = f"""Fiche chantier {MARQUEUR}-2031
Client : Copropriete Les Alizes
Adresse : 14 rue des Peupliers, Merignac
Conducteur de travaux : Benoit Lemoine
Statut : en cours
Avancement : 62 %
Montant du marche : 48 250 EUR HT
Date de demarrage : 12/03/2026
Reception prevue : 30/09/2026
Postes : terrassement 1 200 m2, plantation 340 unites, arrosage automatique 1 lot.
Reserve en cours : reprise du nivellement sur la zone nord.
"""

BLOC_UI = re.compile(r"```ui\s*(.*?)```", re.S)
REQUIS = {"quote": ["client", "total", "lines"], "invoice": ["number", "client", "amount"],
          "table": ["columns", "rows"], "bars": ["data"], "stat": ["label", "value"],
          "callout": ["text"], "email": ["subject", "from"], "list": ["items"],
          "progress": ["items"], "keyvalue": ["rows"], "doc": ["name"],
          "contact": ["name"], "project": ["name", "client"], "badge": ["text"],
          "quick_replies": ["options"]}

# Jetons de masquage qui ne doivent JAMAIS atteindre l'utilisateur : leur
# présence signale un défaut de réhydratation, donc une réponse illisible.
FUITE_JETON = re.compile(r"\[(?:PER|LOC|ORG|MONTANT|TEL|EMAIL|IBAN|DATE|SIRET)_\d+\]")


# ── Analyse d'une réponse ────────────────────────────────────────────

def composants(reponse: str):
    """(types_valides, problemes) — un composant incomplet ne s'affiche pas côté
    interface, il ne compte donc pas comme présent."""
    types, soucis = [], []
    for bloc in BLOC_UI.findall(reponse or ""):
        try:
            d = json.loads(bloc.strip())
        except json.JSONDecodeError as e:
            soucis.append(f"JSON invalide ({e})")
            continue
        requis = REQUIS.get(d.get("type"))
        if requis is None:
            soucis.append(f"type inconnu : {d.get('type')}")
            continue
        manquants = [c for c in requis if d.get(c) in (None, "", [], {})]
        if manquants:
            soucis.append(f"{d.get('type')} incomplet : {manquants}")
            continue
        types.append(d["type"])
    return types, soucis


def _normaliser(texte: str) -> str:
    """Compare des chiffres sans se faire piéger par les espaces d'affichage.

    « 48 250 », « 48 250 » (espace insécable) et « 48250 » désignent le même
    montant : un écart d'espacement n'est pas une erreur de restitution.
    """
    return re.sub(r"[\s  ]+", "", texte or "")


def controles_durs(question: dict, reponse: str, etat: dict, secondes: float,
                   statut: str) -> list[dict]:
    """Contrôles sans modèle. Chacun renvoie {nom, ok, detail}."""
    attendu = question.get("dur") or {}
    resultats = []

    def note(nom, ok, detail=""):
        resultats.append({"nom": nom, "ok": bool(ok), "detail": str(detail)[:300]})

    # Une réponse vide est le pire des échecs : elle passerait tous les
    # contrôles « ne contient pas » sans rien apporter.
    note("réponse non vide", bool((reponse or "").strip()), f"{len(reponse or '')} caractères")

    fuites = FUITE_JETON.findall(reponse or "")
    note("aucun jeton de masquage visible", not fuites, fuites[:5])

    if "max_s" in attendu:
        note(f"latence < {attendu['max_s']} s", secondes <= attendu["max_s"], f"{secondes:.1f} s")

    for extrait in attendu.get("contient", []):
        note(f"restitue « {extrait} »", _normaliser(extrait) in _normaliser(reponse),
             "absent de la réponse")

    for extrait in attendu.get("interdit", []):
        note(f"ne contient pas « {extrait} »", extrait not in (reponse or ""),
             "présent alors qu'il ne devrait pas")

    if "composant" in attendu:
        voulus = attendu["composant"]
        voulus = [voulus] if isinstance(voulus, str) else voulus
        types, soucis = composants(reponse)
        note(f"composant {'/'.join(voulus)} affichable",
             any(t in voulus for t in types),
             f"trouvés : {types or 'aucun'}" + (f" | {soucis}" if soucis else ""))

    if "recherche" in attendu:
        cherche = bool(etat.get("besoin_memoire"))
        note("recherche mémoire " + ("déclenchée" if attendu["recherche"] else "évitée"),
             cherche == attendu["recherche"],
             f"routeur : besoin_memoire={cherche}")

    if "statut" in attendu:
        note(f"statut = {attendu['statut']}", statut == attendu["statut"], statut)

    return resultats


# ── Juge ─────────────────────────────────────────────────────────────

INVITE_JUGE = """Tu évalues la réponse d'un assistant d'entreprise face à un critère écrit à l'avance.
Sois STRICT sur le fond et indulgent sur la forme : une réponse correcte mais formulée
autrement satisfait le critère. Une réponse qui invente une donnée ne le satisfait jamais.

CRITÈRE : {critere}

QUESTION POSÉE : {question}

RÉPONSE DE L'ASSISTANT :
{reponse}

Réponds par un objet JSON seul : {{"ok": true|false, "motif": "<une phrase>"}}"""


async def juger(question: dict, reponse: str) -> dict:
    from langchain_core.messages import HumanMessage
    from llm.router import get_llm, LLMTier

    critere = question.get("juge")
    if not critere:
        return {"ok": None, "motif": "aucun critère"}
    try:
        llm = get_llm(LLMTier.COMPLEX)
        sortie = await llm.ainvoke([HumanMessage(content=INVITE_JUGE.format(
            critere=critere, question=question["question"], reponse=(reponse or "")[:4000]))])
        trouve = re.search(r"\{.*\}", str(sortie.content), re.S)
        data = json.loads(trouve.group(0)) if trouve else {}
        return {"ok": bool(data.get("ok")), "motif": str(data.get("motif") or "")[:300]}
    except Exception as e:  # noqa: BLE001 - un juge en panne ne casse pas la campagne
        return {"ok": None, "motif": f"juge indisponible : {e}"}


# ── Exécution ────────────────────────────────────────────────────────

async def preparer(args) -> dict:
    """Ingère le document de référence et récupère un compte réel."""
    from database.connection import get_db
    from ingestion.pipeline import ingest_document

    chunks = await ingest_document(
        text=DOC_TEST, source_type=SOURCE_TEST, source_id=f"{SOURCE_TEST}:2031",
        source_filename=f"{MARQUEUR}-2031.txt", access_level="all")
    print(f"{GRIS}document de référence ingéré ({chunks} fragments){RAZ}")

    async with get_db() as conn:
        for role in ("super_admin", "direction"):
            u = await conn.fetchrow(
                "SELECT id, email, role FROM users WHERE role = $1 AND actif LIMIT 1", role)
            if u:
                return dict(u)
        u = await conn.fetchrow("SELECT id, email, role FROM users WHERE actif LIMIT 1")
    if not u:
        raise SystemExit("Aucun utilisateur actif en base — impossible de lancer la campagne.")
    return dict(u)


async def nettoyer():
    from database.connection import get_db
    async with get_db() as conn:
        await conn.execute("DELETE FROM documents WHERE source_type = $1", SOURCE_TEST)


async def poser(question: dict, fil: str, utilisateur: dict) -> tuple[str, dict, float, str]:
    """Un tour complet. Renvoie (réponse, état final, secondes, statut)."""
    from agents import runtime

    debut = time.monotonic()
    res = await runtime.run_turn(
        query=question["question"], user_id=str(utilisateur["id"]),
        user_role=utilisateur["role"], has_attachment=False, thread_id=fil,
        trigger_kind="chat")
    secondes = time.monotonic() - debut

    # L'état du graphe porte ce que la réponse ne dit pas : la décision du
    # routeur, les actions réellement exécutées. C'est ce qui permet de vérifier
    # qu'un « bonjour » n'a PAS déclenché de recherche.
    etat = {}
    try:
        graph = await runtime.get_graph()
        snap = await graph.aget_state(runtime._graph_config(fil, str(utilisateur["id"])))
        etat = snap.values if isinstance(snap.values, dict) else {}
    except Exception:  # noqa: BLE001 - l'introspection ne doit pas faire échouer le tour
        pass

    return res.get("response") or "", etat, secondes, res.get("status") or "?"


async def campagne(args):
    banque = json.load(open(os.path.join(ICI, "banque.json"), encoding="utf-8"))
    questions = banque["questions"]
    if args.categorie:
        questions = [q for q in questions if q["categorie"] == args.categorie]
    if args.limite:
        questions = questions[:args.limite]
    if not questions:
        raise SystemExit("Aucune question ne correspond au filtre.")

    appels = len(questions) * (1 if args.sans_juge else 2)
    print(f"\n{JAUNE}Campagne : {len(questions)} question(s), "
          f"~{appels} appels au modèle, pause {args.pause}s.{RAZ}\n")

    utilisateur = await preparer(args)
    print(f"{GRIS}compte utilisé : {utilisateur['email']} ({utilisateur['role']}){RAZ}\n")

    # Les questions partageant un `fil` gardent la MÊME conversation : c'est ce
    # qui permet de tester la mémoire d'un tour à l'autre.
    fils: dict[str, str] = {}
    resultats = []

    for i, q in enumerate(questions, 1):
        cle = q.get("fil")
        fil = fils.setdefault(cle, f"bench-{uuid.uuid4()}") if cle else f"bench-{uuid.uuid4()}"

        try:
            reponse, etat, secondes, statut = await poser(q, fil, utilisateur)
        except Exception as e:  # noqa: BLE001
            print(f"  {ROUGE}KO{RAZ}   [{q['id']}] tour en échec : {e}")
            resultats.append({"id": q["id"], "categorie": q["categorie"],
                              "question": q["question"], "erreur": str(e)[:300],
                              "durs": [], "juge": {"ok": False, "motif": "tour en échec"},
                              "secondes": 0, "reponse": ""})
            continue

        durs = controles_durs(q, reponse, etat, secondes, statut)
        verdict_juge = {"ok": None, "motif": "désactivé"} if args.sans_juge else await juger(q, reponse)

        rates = [c for c in durs if not c["ok"]]
        marque = (ROUGE + "KO" if rates else
                  (JAUNE + "~~" if verdict_juge["ok"] is False else VERT + "OK")) + RAZ
        print(f"  {marque}   [{q['id']}] {q['question'][:56]:<56} {secondes:5.1f}s")
        for c in rates:
            print(f"       {GRIS}· {c['nom']} — {c['detail']}{RAZ}")
        if verdict_juge["ok"] is False:
            print(f"       {GRIS}· juge : {verdict_juge['motif']}{RAZ}")

        resultats.append({"id": q["id"], "categorie": q["categorie"],
                          "question": q["question"], "durs": durs, "juge": verdict_juge,
                          "secondes": round(secondes, 2), "statut": statut,
                          "recherche": bool(etat.get("besoin_memoire")),
                          "reponse": reponse[:3000]})

        if i < len(questions) and args.pause:
            await asyncio.sleep(args.pause)

    if not args.garder:
        await nettoyer()
    return resultats


# ── Rapport ──────────────────────────────────────────────────────────

def _score(r: dict) -> tuple[int, int]:
    durs = r.get("durs") or []
    return sum(1 for c in durs if c["ok"]), len(durs)


def rapport(resultats: list[dict]) -> str:
    os.makedirs(RAPPORTS, exist_ok=True)
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    chemin = os.path.join(RAPPORTS, f"{horodatage}.json")

    reussis = sum(1 for r in resultats if all(c["ok"] for c in (r.get("durs") or [])))
    juge_ko = [r for r in resultats if (r.get("juge") or {}).get("ok") is False]
    latences = [r["secondes"] for r in resultats if r.get("secondes")]

    resume = {
        "horodatage": horodatage,
        "questions": len(resultats),
        "sans_faute": reussis,
        "juge_ko": len(juge_ko),
        "latence_mediane": round(statistics.median(latences), 1) if latences else 0,
        "latence_max": round(max(latences), 1) if latences else 0,
    }
    json.dump({"resume": resume, "resultats": resultats},
              open(chemin, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n{JAUNE}── Résumé {'─' * 46}{RAZ}")
    print(f"  {reussis}/{len(resultats)} questions sans aucun contrôle en échec")
    if not any((r.get("juge") or {}).get("ok") is None for r in resultats):
        print(f"  {len(juge_ko)} réponse(s) jugées hors critère")
    print(f"  latence médiane {resume['latence_mediane']} s, maximum {resume['latence_max']} s")

    # Par catégorie : c'est là qu'on voit OÙ ça casse.
    cats: dict[str, list[dict]] = {}
    for r in resultats:
        cats.setdefault(r["categorie"], []).append(r)
    print(f"\n  {GRIS}par catégorie :{RAZ}")
    for cat, items in sorted(cats.items()):
        ok = sum(_score(r)[0] for r in items)
        total = sum(_score(r)[1] for r in items)
        print(f"    {cat:<14} {ok:>3}/{total:<3} contrôles")

    # Comparaison avec le run précédent : le vrai intérêt de la banque figée.
    precedents = sorted(f for f in os.listdir(RAPPORTS)
                        if f.endswith(".json") and f != os.path.basename(chemin))
    if precedents:
        ancien = json.load(open(os.path.join(RAPPORTS, precedents[-1]), encoding="utf-8"))
        avant = {r["id"]: _score(r) for r in ancien["resultats"]}
        regressions, corrections = [], []
        for r in resultats:
            ok, total = _score(r)
            if r["id"] not in avant:
                continue
            ok_avant, _ = avant[r["id"]]
            if ok < ok_avant:
                regressions.append(f"{r['id']} ({ok_avant} → {ok})")
            elif ok > ok_avant:
                corrections.append(f"{r['id']} ({ok_avant} → {ok})")
        print(f"\n  {GRIS}vs {precedents[-1]} :{RAZ}")
        print(f"    {ROUGE}{len(regressions)} régression(s){RAZ}"
              + (f" : {', '.join(regressions[:8])}" if regressions else ""))
        print(f"    {VERT}{len(corrections)} correction(s){RAZ}"
              + (f" : {', '.join(corrections[:8])}" if corrections else ""))
    else:
        print(f"\n  {GRIS}premier run : aucune comparaison possible.{RAZ}")

    print(f"\n  rapport détaillé : {chemin}")
    return chemin


def main():
    p = argparse.ArgumentParser(description="Banc de campagne — pertinence des réponses")
    p.add_argument("--categorie")
    p.add_argument("--limite", type=int)
    p.add_argument("--pause", type=float, default=2.0)
    p.add_argument("--sans-juge", action="store_true")
    p.add_argument("--garder", action="store_true")
    args = p.parse_args()

    async def _run():
        from database.connection import init_db
        from agents.runtime import init_runtime, shutdown_runtime
        await init_db()
        await init_runtime()
        try:
            return await campagne(args)
        finally:
            await shutdown_runtime()

    resultats = asyncio.run(_run())
    rapport(resultats)
    en_echec = sum(1 for r in resultats if any(not c["ok"] for c in (r.get("durs") or [])))
    sys.exit(1 if en_echec else 0)


if __name__ == "__main__":
    main()
