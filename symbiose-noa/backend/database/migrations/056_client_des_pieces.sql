-- LE CLIENT DE CHAQUE PIÈCE (17/09) : sans lui, ni chiffre d'affaires par client, ni « la dernière
-- prestation réalisée chez lui ». Lu dans le bloc d'adresse du PDF. `dossier_id` : le dossier du
-- classement où vit le fichier, pour dire son chemin. Colonnes additives, idempotente.
ALTER TABLE pieces_chiffrees ADD COLUMN IF NOT EXISTS client TEXT;
ALTER TABLE pieces_chiffrees ADD COLUMN IF NOT EXISTS code_client TEXT;
ALTER TABLE pieces_chiffrees ADD COLUMN IF NOT EXISTS dossier_id TEXT;
CREATE INDEX IF NOT EXISTS idx_pieces_chiffrees_date ON pieces_chiffrees(date_piece);
