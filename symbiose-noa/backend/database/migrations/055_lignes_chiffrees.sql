-- LA BASE DE PRIX DE LA MAISON (17/09) : les LIGNES des devis et factures émis, lues dans
-- les PDF du classement (désignation, unité, quantité, prix unitaire HT). Les jeux importés
-- ne portent que des totaux par affaire : sans ces lignes, aucune estimation n'est possible.
-- Tables additives : rien d'existant n'est modifié. Idempotente.
CREATE TABLE IF NOT EXISTS pieces_chiffrees(
    fichier_id   TEXT PRIMARY KEY,           -- identifiant du fichier dans le classement
    fichier_nom  TEXT NOT NULL,
    modifie_le   TIMESTAMPTZ,                -- date du fichier : une pièce inchangée n'est pas relue
    etat         TEXT NOT NULL,              -- lue | pas_de_la_maison | illisible | trop_lourde
    nature       TEXT,                       -- devis | facture | avoir | commande | situation
    numero       TEXT,
    date_piece   DATE,
    titre        TEXT,
    total_ht     NUMERIC(14,2),
    somme_lignes NUMERIC(14,2),
    controle     TEXT,                       -- juste | ecart | sans_total : la somme des lignes retrouve-t-elle le total ?
    methode      TEXT,                       -- texte | ocr
    lignes       INTEGER NOT NULL DEFAULT 0,
    access_level TEXT NOT NULL,
    lu_le        TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS lignes_chiffrees(
    id           BIGSERIAL PRIMARY KEY,
    fichier_id   TEXT NOT NULL REFERENCES pieces_chiffrees(fichier_id) ON DELETE CASCADE,
    rang         INTEGER NOT NULL,
    designation  TEXT NOT NULL,
    rubrique     TEXT NOT NULL DEFAULT '',
    texte_plat   TEXT NOT NULL,              -- rubrique + désignation, sans accents ni casse : c'est lui qu'on cherche
    unite        TEXT NOT NULL DEFAULT '',
    quantite     NUMERIC(14,4) NOT NULL,
    pu_ht        NUMERIC(14,4) NOT NULL,
    montant_ht   NUMERIC(14,2) NOT NULL,
    tva          NUMERIC(6,2));
CREATE INDEX IF NOT EXISTS idx_lignes_chiffrees_fichier ON lignes_chiffrees(fichier_id);
CREATE INDEX IF NOT EXISTS idx_lignes_chiffrees_texte ON lignes_chiffrees USING gin (texte_plat gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_pieces_chiffrees_numero ON pieces_chiffrees(numero);
REVOKE ALL ON pieces_chiffrees, lignes_chiffrees FROM infra_ia_lecteur_rls;
