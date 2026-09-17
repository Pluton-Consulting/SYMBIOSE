"""Connexion par adresse : routes réelles, base/session doublées, aucun mail envoyé."""
import ast, asyncio, pathlib, sys, unittest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

BACKEND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'backend').resolve()
sys.argv = [sys.argv[0]]

class Refus(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail

class Connexion(unittest.TestCase):
    def setUp(self):
        self.compte = {'id': 'compte-autorise', 'email': 'Test@Exemple.fr', 'role': 'utilisateur', 'actif': True}
        self.comptes = [self.compte]
        self.ecritures = []
        async def fetch(sql, email):
            self.assertIn('actif = true', sql)
            self.assertIn('LIMIT 2', sql)
            return [x for x in self.comptes if x['email'].strip().lower() == email and x['actif']][:2]
        async def execute(sql, *args):
            self.ecritures.append((sql,args))
        @asynccontextmanager
        async def base():
            yield SimpleNamespace(fetch=fetch, execute=execute)
        self.appareil = SimpleNamespace(creer=AsyncMock(return_value='session-test'), compte_de=AsyncMock(return_value=None))
        self.audit = AsyncMock()
        self.tentatives = SimpleNamespace(origine_de=lambda h,c:h or c, saturee=Mock(return_value=False), noter_echec=Mock(), oublier=Mock())
        self.jwt = Mock(return_value='jwt-test')
        ns = {'get_db':base, 'datetime':datetime, 'timezone':timezone, 'tentatives':self.tentatives,
              'appareil':self.appareil, 'log_action':self.audit, 'create_access_token':self.jwt,
              'HTTPException':Refus, 'status':SimpleNamespace(HTTP_429_TOO_MANY_REQUESTS=429,HTTP_403_FORBIDDEN=403,HTTP_410_GONE=410,HTTP_401_UNAUTHORIZED=401),
              'ConnexionEmailRequest':object, 'RefreshRequest':object, 'Request':object}
        nodes = [n for n in ast.parse((BACKEND/'routers/auth.py').read_text()).body if isinstance(n,ast.AsyncFunctionDef) and n.name in ('connexion_email','lien_magique_retire','refresh_session')]
        self.assertEqual(len(nodes),3)
        for n in nodes:n.decorator_list=[]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'routes_reelles','exec'),ns)
        self.ns=ns
        self.request=SimpleNamespace(headers={'user-agent':'Navigateur test'},client=SimpleNamespace(host='127.0.0.1'))
    def appeler(self, email='  TEST@EXEMPLE.FR  '):
        return asyncio.run(self.ns['connexion_email'](SimpleNamespace(email=email),self.request))
    def test_compte_existant_role_et_session_conserves(self):
        r=self.appeler();self.assertEqual(r['id'],self.compte['id']);self.assertEqual(r['email'],self.compte['email'])
        self.assertEqual(r['role'],'utilisateur');self.assertEqual(r['refresh_token'],'session-test')
        self.jwt.assert_called_once_with({'sub':'compte-autorise','role':'utilisateur'})
        self.assertEqual(len(self.ecritures),1);self.assertTrue(self.ecritures[0][0].startswith('UPDATE users SET last_login'))
        self.appareil.creer.assert_awaited_once_with('compte-autorise','Navigateur test')
    def test_adresse_inconnue_ne_cree_ni_compte_ni_session(self):
        with self.assertRaises(Refus) as c:self.appeler('absent@exemple.fr')
        self.assertEqual(c.exception.status_code,403);self.assertEqual(self.ecritures,[]);self.appareil.creer.assert_not_called();self.jwt.assert_not_called()
    def test_compte_desactive_refuse(self):
        self.compte['actif']=False
        with self.assertRaises(Refus) as c:self.appeler()
        self.assertEqual(c.exception.status_code,403);self.appareil.creer.assert_not_called()
    def test_adresse_ambigue_refuse_choix_arbitraire(self):
        self.comptes.append({**self.compte,'id':'autre','role':'admin','email':'test@exemple.fr'})
        with self.assertRaises(Refus) as c:self.appeler()
        self.assertEqual(c.exception.status_code,403);self.jwt.assert_not_called()
    def test_origine_bornee_avant_session(self):
        self.tentatives.saturee.return_value=True
        with self.assertRaises(Refus) as c:self.appeler()
        self.assertEqual(c.exception.status_code,429);self.appareil.creer.assert_not_called();self.assertEqual(self.ecritures,[])
    def test_anciens_liens_refuses_sans_mail(self):
        with self.assertRaises(Refus) as c:asyncio.run(self.ns['lien_magique_retire']())
        self.assertEqual(c.exception.status_code,410);self.appareil.creer.assert_not_called();self.assertEqual(self.ecritures,[])
    def test_session_revoquee_reste_refusee(self):
        with self.assertRaises(Refus) as c:asyncio.run(self.ns['refresh_session'](SimpleNamespace(refresh_token='revoque')))
        self.assertEqual(c.exception.status_code,401);self.jwt.assert_not_called()

unittest.main(verbosity=2)
