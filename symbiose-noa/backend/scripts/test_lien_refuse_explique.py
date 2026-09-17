"""Point d’entrée historique : le lien est retiré depuis la demande du 17/09.
La recette couvre maintenant son refus 410 et la connexion par adresse.
"""
import pathlib, runpy
runpy.run_path(str(pathlib.Path(__file__).with_name('test_connexion_email.py')),run_name='__main__')
