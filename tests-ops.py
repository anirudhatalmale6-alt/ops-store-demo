# -*- coding: utf-8 -*-
"""Controles du catalogue OPS : le fichier d'import et la vitrine.

Tout est RECALCULE depuis ops_store_data (5).csv. Aucun chiffre n'est repris
du generateur : si build.py se trompe, ces controles doivent le voir.

    python3 tests-ops.py            -> vitrine locale (demo/index.html)
    python3 tests-ops.py <url>      -> vitrine publiee
"""

import csv, io, json, os, re, sys, collections, threading, functools
import rayons
from rayons import lire, vide

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_OUT = os.path.join(HERE, 'import', 'ops-produits.csv')
DEMO = os.path.join(HERE, 'demo')


def servir():
    """Sert demo/ en HTTP le temps des controles.

    Pas un confort : la page lit son catalogue avec fetch(), et fetch() sur
    une origine « file:// » est refuse par le navigateur. Ouvert au fichier,
    l'ecran reste vide et les controles echouent tous sur « Failed to fetch »
    alors que la page est bonne. Un test qui n'a raison qu'a condition qu'on
    ait pense a lancer un serveur a cote n'est pas un test."""
    import http.server, socketserver
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DEMO)
    h.log_message = lambda *a, **k: None
    srv = socketserver.TCPServer(('127.0.0.1', 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, 'http://127.0.0.1:%d' % srv.server_address[1]


SERVEUR = None
if len(sys.argv) > 1:
    BASE = sys.argv[1].rstrip('/')
else:
    SERVEUR, BASE = servir()

ok = bad = 0


def t(label, cond, detail=''):
    global ok, bad
    if cond:
        ok += 1
        print('  ok    %s' % label)
    else:
        bad += 1
        print('  ECHEC %s   %s' % (label, detail))


# --- la verite, recalculee depuis la source --------------------------------
SRC = lire()
SRC_NOMMES = [l for l in SRC if not vide(l.get('Product Name'))]


def langue(l):
    return 'en' if '/en/' in l['URL'] else 'fr'


groupes = collections.defaultdict(list)
for l in SRC_NOMMES:
    groupes[l['Reference']].append(l)
ATTENDU = len(groupes)
DOUBLONS = len(SRC_NOMMES) - ATTENDU
SANS_NOM = len(SRC) - len(SRC_NOMMES)


def prix(v):
    if vide(v):
        return None
    s = re.sub(r'[^\d.,]', '', v.replace(' ', '').replace('\xa0', ''))
    if s.count(',') == 1 and s.count('.') == 0:
        s = s.replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


# Les comptes attendus se calculent sur les fiches RETENUES, pas sur les
# 8 474 lignes : sinon un doublon sans prix serait compte deux fois.
def retenue(grp):
    return sorted(grp, key=lambda x: (langue(x) != 'en', '.fr/' in x['URL']))[0]


RETENUES = [retenue(g) for g in groupes.values()]
SANS_PRIX = sum(1 for l in RETENUES if prix(l['Price']) is None)
SANS_DESC = sum(1 for l in RETENUES if vide(l['Description']))

print('\n=== source ===')
print('  %d lignes, %d nommees, %d references distinctes'
      % (len(SRC), len(SRC_NOMMES), ATTENDU))
print('  attendu : %d doublons, %d sans nom, %d sans prix, %d sans description'
      % (DOUBLONS, SANS_NOM, SANS_PRIX, SANS_DESC))

# --- 1. l'encodage ---------------------------------------------------------
print('\n=== 1. encodage de la source ===')
BRUT = open(rayons.CSV, 'rb').read()
try:
    BRUT.decode('utf-8')
    t('le fichier n\'est pas de l\'UTF-8', False, 'il se decode en UTF-8')
except UnicodeDecodeError:
    t('le fichier n\'est pas de l\'UTF-8', True)
t('l\'octet 0x80 est present (c\'est « € » en CP1252)', b'\x80' in BRUT)
# Le meme fichier lu en Latin-1 : le symbole monetaire devient un caractere
# de controle. C'est la difference que « Latin-1 » cachait.
lat = BRUT[:200000].decode('latin-1')
cp = BRUT[:200000].decode('cp1252')
t('lu en Latin-1, le symbole monetaire devient un caractere de controle',
  '\x80' in lat and '€' in cp and '€' not in lat)

# --- 2. le fichier d'import ------------------------------------------------
print('\n=== 2. fichier d\'import WooCommerce ===')
b = open(CSV_OUT, 'rb').read()
t('le fichier commence par le BOM, sans rien devant',
  b.startswith(b'\xEF\xBB\xBF'), repr(b[:60]))
t('aucun HTML dans le fichier', b'<b>' not in b and b'<br' not in b)
IMP = list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
t('%d articles, soit une ligne par reference' % ATTENDU, len(IMP) == ATTENDU,
  str(len(IMP)))
t('les UGS sont toutes uniques', len({r['SKU'] for r in IMP}) == len(IMP),
  '%d uniques' % len({r['SKU'] for r in IMP}))
t('aucune UGS vide', all(r['SKU'].strip() for r in IMP))
t('tous les articles sont de type « external » (affiliation)',
  all(r['Type'] == 'external' for r in IMP),
  str(collections.Counter(r['Type'] for r in IMP)))
t('chaque article porte son adresse de destination',
  all(r['External URL'].startswith('http') for r in IMP))
t('aucun intitule vide', all(r['Name'].strip() for r in IMP))

# LE point du fichier : « N/A » ne doit jamais franchir le generateur.
na_desc = [r for r in IMP if r['Description'].strip().upper() in ('N/A', 'NA')]
t('aucune description ne vaut « N/A »', not na_desc,
  '%d fiches' % len(na_desc))
na_prix = [r for r in IMP if r['Regular price'].strip().upper() in ('N/A', 'NA')]
t('aucun prix ne vaut « N/A »', not na_prix, '%d fiches' % len(na_prix))
zero = [r for r in IMP if r['Regular price'].strip() in ('0', '0.00', '0,00')]
t('aucun article n\'est tombe a 0,00 € (le piege du « N/A »)', not zero,
  '%d fiches' % len(zero))

vides = [r for r in IMP if not r['Regular price'].strip()]
t('les %d articles sans prix ont un prix VIDE, pas un prix nul'
  % SANS_PRIX, len(vides) == SANS_PRIX, str(len(vides)))
t('et ils partent en brouillon, pas en ligne',
  all(r['Published'] == '0' for r in vides))
t('tous les autres sont publies',
  all(r['Published'] == '1' for r in IMP if r['Regular price'].strip()))

sd = [r for r in IMP if not r['Description'].strip()]
t('les %d articles sans description ont une description VIDE' % SANS_DESC,
  len(sd) == SANS_DESC, str(len(sd)))

# Le dedoublonnage doit avoir choisi l'anglais.
refs_doubles = [k for k, g in groupes.items() if len(g) > 1]
t('%d references etaient en double dans la source' % DOUBLONS,
  len(refs_doubles) == DOUBLONS, str(len(refs_doubles)))
par_sku = {r['SKU']: r for r in IMP}
mauvais = [k for k in refs_doubles
           if any(langue(x) == 'en' for x in groupes[k])
           and '/en/' not in par_sku[k]['External URL']]
t('sur chaque doublon FR/EN, c\'est la fiche anglaise qui est retenue',
  not mauvais, str(mauvais[:3]))

# La colonne « Image » du fournisseur contenait 214 fichiers .mp4. Recensement
# complet (pas echantillon) : les 214 repondent 404. Ils doivent avoir disparu
# du fichier d'import, et l'enjeu n'est pas cosmetique — WooCommerce leve une
# Exception sur une image introuvable AVANT d'enregistrer le produit
# (abstract-wc-product-importer.php : set_image_data() puis $object->save()),
# donc ces 214 liens faisaient rater 171 FICHES entieres, pas 171 vignettes.
toutes_img = []
for r in IMP:
    toutes_img += [x.strip() for x in (r.get('Images') or '').split(',') if x.strip()]
NON_IMG = ('.mp4', '.mov', '.avi', '.webm', '.wmv', '.mkv', '.pdf', '.zip')
intrus = [u for u in toutes_img if u.split('?')[0].lower().endswith(NON_IMG)]
t('aucun fichier non-image dans la colonne Images', not intrus, str(intrus[:2]))
t('toutes les images sont en http(s)',
  all(u.startswith('http') for u in toutes_img), str(len(toutes_img)))
# Les noms de fichiers servent de noms locaux au rapatriement : une collision
# ecraserait silencieusement une image par une autre.
bases = [u.rsplit('/', 1)[-1].split('?')[0] for u in set(toutes_img)]
t('les %d noms de fichiers images sont uniques (aucune collision au rapatriement)'
  % len(bases), len(set(bases)) == len(bases),
  '%d noms pour %d liens' % (len(set(bases)), len(bases)))

# --- 3. les rayons ---------------------------------------------------------
print('\n=== 3. rayons ===')
lib = dict([(r[0], r[1]) for r in rayons.RAYONS] + [rayons.FOURRE_TOUT])
attendu_rayons = collections.Counter(
    rayons.classer(l)[1] for l in RETENUES)
reel = collections.Counter(r['Categories'] for r in IMP)
t('chaque article a un rayon', all(r['Categories'].strip() for r in IMP))
t('les rayons du fichier d\'import correspondent au classement recalcule',
  reel == attendu_rayons,
  str((set(reel) ^ set(attendu_rayons)) or
      [(k, reel[k], attendu_rayons[k]) for k in reel
       if reel[k] != attendu_rayons[k]][:3]))
t('aucun rayon n\'est vide', all(v > 0 for v in reel.values()))
t('le fourre-tout reste minoritaire (moins de 10 %)',
  reel[rayons.FOURRE_TOUT[1]] < 0.10 * len(IMP),
  '%d / %d' % (reel[rayons.FOURRE_TOUT[1]], len(IMP)))

# Un rayon qui absorbe tout serait un classement rate, pas un classement.
gros = max(reel.values())
t('aucun rayon n\'absorbe plus du tiers du catalogue',
  gros < len(IMP) / 3.0, '%d / %d' % (gros, len(IMP)))

# --- 4. le catalogue de la vitrine ----------------------------------------
print('\n=== 4. catalogue de la vitrine ===')
CAT = json.load(open(os.path.join(DEMO, 'catalogue.json'), encoding='utf-8'))
t('la vitrine contient les memes %d articles' % ATTENDU,
  len(CAT['p']) == ATTENDU, str(len(CAT['p'])))
t('les references de la vitrine et de l\'import sont identiques',
  {x['r'] for x in CAT['p']} == {r['SKU'] for r in IMP})
t('les %d articles sans prix portent null, jamais 0' % SANS_PRIX,
  sum(1 for x in CAT['p'] if x['p'] is None) == SANS_PRIX
  and not [x for x in CAT['p'] if x['p'] == 0],
  str(sum(1 for x in CAT['p'] if x['p'] is None)))
t('chaque article a une adresse vers la boutique d\'origine',
  all(x['u'].startswith('http') for x in CAT['p']))
t('les rayons annonces correspondent aux articles',
  all(r['n'] == sum(1 for x in CAT['p'] if x['c'] == r['id'])
      for r in CAT['r']))
t('la somme des rayons fait le catalogue entier',
  sum(r['n'] for r in CAT['r']) == len(CAT['p']),
  str(sum(r['n'] for r in CAT['r'])))

# --- 5. la page ------------------------------------------------------------
print('\n=== 5. la page ===')
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('  (Playwright absent, section sautee)')
else:
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        p = br.new_page()
        p.set_viewport_size({'width': 1280, 'height': 900})
        errs = []
        p.on('pageerror', lambda e: errs.append(str(e)))
        p.goto(BASE + '/index.html', wait_until='networkidle')
        p.wait_for_timeout(2500)

        t('aucune erreur JS', not errs, str(errs[:2]))
        t('la page annonce les %d articles' % ATTENDU,
          p.inner_text('#vu').strip() == str(ATTENDU), p.inner_text('#vu'))
        t('un select par rayon, plus « tous »',
          p.eval_on_selector_all('#cat option', 'e=>e.length')
          == len(CAT['r']) + 1)

        # Un plafond de prix ne doit pas escamoter les articles sans prix :
        # c'est exactement le defaut trouve sur le filtre DA d'Influus, et il
        # se reproduit ici a l'identique si on lit « pas de prix » comme 0.
        p.fill('#pmax', '25')
        p.wait_for_timeout(700)
        gardes = p.evaluate("filtrer().filter(x=>x.p===null).length")
        t('un plafond de prix garde les %d articles sans prix' % SANS_PRIX,
          gardes == SANS_PRIX, str(gardes))
        chers = p.evaluate("filtrer().filter(x=>x.p!==null&&x.p>25).length")
        t('et il ecarte bien tout ce qui depasse le plafond', chers == 0,
          str(chers))

        p.fill('#pmax', '')
        p.select_option('#tri', 'px')
        p.wait_for_timeout(700)
        q = p.evaluate("filtrer().map(x=>x.p===null?1:0)")
        t('tri par prix : les articles sans prix finissent en bas',
          q == sorted(q))
        px = p.evaluate("filtrer().filter(x=>x.p!==null).map(x=>x.p)")
        t('tri par prix : les prix sont bien croissants', px == sorted(px))

        p.select_option('#tri', 'nom')
        p.select_option('#cat', 'optiques')
        p.wait_for_timeout(700)
        n = int(p.inner_text('#vu'))
        att = [r['n'] for r in CAT['r'] if r['id'] == 'optiques'][0]
        t('le filtre « optiques » rend les %d articles annonces' % att,
          n == att, str(n))

        p.select_option('#cat', '')
        p.fill('#q', 'zzzznexistepas')
        p.wait_for_timeout(600)
        t('une recherche sans resultat affiche le message, pas une grille vide',
          p.is_visible('#vide') and p.inner_text('#vu').strip() == '0')

        p.fill('#q', '')
        p.wait_for_timeout(600)
        for w, h in ((1280, 900), (390, 780)):
            p.set_viewport_size({'width': w, 'height': h})
            p.wait_for_timeout(500)
            deb = p.evaluate('document.documentElement.scrollWidth>'
                             'document.documentElement.clientWidth')
            t('aucun debordement horizontal en %dpx' % w, not deb)
            # Le padding lateral avait disparu en 390 : « .top » est declare
            # apres « .wrap » et, a specificite egale, ecrasait son padding.
            xs = [p.eval_on_selector(s, 'e=>Math.round('
                                     'e.getBoundingClientRect().x)')
                  for s in ('.logo', '#q', '.card')]
            t('en %dpx, entete, filtres et grille sont alignes' % w,
              len(set(xs)) == 1, str(xs))

        br.close()

if SERVEUR:
    SERVEUR.shutdown()

print('\n%d controles, %d verts, %d rouges' % (ok + bad, ok, bad))
sys.exit(1 if bad else 0)
