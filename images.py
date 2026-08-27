# -*- coding: utf-8 -*-
"""Mesure le parc d'images du catalogue OPS — sans rapatrier les images.

POURQUOI CE FICHIER EXISTE. « Telecharge les images » suppose qu'on sache ce
qu'on telecharge. Mon premier chiffre (~1,8 Go) venait d'un echantillon de 20
fichiers : c'est une intuition, pas une mesure. Ici on interroge les entetes
(HEAD) d'un echantillon large et TIRE AU SORT DE FACON REPRODUCTIBLE, ce qui
donne trois choses qu'un echantillon de 20 ne donne pas :

  1. un poids total avec sa marge d'erreur, et non un nombre nu ;
  2. le taux de liens MORTS — c'est le chiffre qui decide de tout. Importer
     20 000 images dont une part repond 404 laisse des fiches produit cassees,
     et on ne le decouvre qu'apres l'import ;
  3. le poids de la PLUS GROSSE image, qui dit si l'hebergement mutualise
     tiendra la conversion.

Une requete HEAD ne transfere pas le fichier : elle demande ses entetes. Le
cout reseau est de l'ordre du kilo-octet par image, pas du mega-octet. C'est
la difference entre mesurer un entrepot et le vider.

    python3 images.py            # echantillon par defaut
    python3 images.py 400        # echantillon plus large
    python3 images.py --liste    # ecrit la liste complete des URL (1 par ligne)
"""

import csv, os, random, sys, collections
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
IMPORT = os.path.join(HERE, 'import', 'ops-produits.csv')
SORTIE = os.path.join(HERE, 'import', 'ops-images.txt')

# Graine FIXE : deux executions doivent tirer le meme echantillon, sinon le
# chiffre change a chaque relance et on ne peut plus le citer.
GRAINE = 40478471
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


def urls():
    """Les URL d'images des lignes REELLEMENT importees.

    On lit le fichier d'import, pas le CSV source : le source contient aussi
    les 33 doublons FR/EN ecartes, dont les images ne seront jamais demandees.
    Mesurer le source gonflerait le total sans que personne ne telecharge
    ces octets."""
    tout, par_fiche = [], []
    with open(IMPORT, encoding='utf-8-sig', newline='') as f:
        for l in csv.DictReader(f):
            u = [x.strip() for x in (l.get('Images') or '').split(',') if x.strip()]
            par_fiche.append(len(u))
            tout.extend(u)
    return tout, par_fiche


def entete(u, timeout=20):
    """(statut, octets, type) — octets vaut None si le poids reste inconnu.

    On suit les redirections (urllib le fait seul) et on renvoie le statut
    FINAL : une image derriere un 301 n'est pas un lien mort.

    DEUX PASSES, parce que ce serveur-ci ne coopere pas. Sur une requete HEAD
    il ne renvoie AUCUN « Content-Length » — mesure : 0 sur 250. Un HEAD seul
    aurait donc conclu « poids inconnu » et je serais reste sur mon estimation
    au doigt mouille.

    La seconde passe demande le PREMIER OCTET (« Range: bytes=0-0 »). Le
    serveur repond alors 206 avec « Content-Range: bytes 0-0/123456 », ou le
    nombre apres la barre est le poids reel du fichier. Cout : un octet de
    corps. C'est la seule facon de peser sans telecharger."""
    req = urllib.request.Request(u, method='HEAD', headers={'User-Agent': UA})
    statut, taille, ctype = None, None, ''
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            statut = r.status
            ctype = r.headers.get('Content-Type', '')
            cl = r.headers.get('Content-Length')
            if cl and cl.isdigit():
                taille = int(cl)
    except urllib.error.HTTPError as e:
        return e.code, None, ''
    except Exception as e:
        return type(e).__name__, None, ''

    return statut, taille, ctype


# Plafond de securite : on mesure un ECHANTILLON, on ne rapatrie pas le parc.
# Si ce compteur est atteint, la mesure s arrete et le dit — mieux vaut une
# mesure incomplete annoncee qu un telechargement de masse involontaire.
PLAFOND_OCTETS = 60 * 1024 * 1024
_lus = [0]


def poids_reel(u, timeout=30):
    """Poids d un fichier, en LISANT le corps. (octets, statut)

    POURQUOI IL FAUT EN ARRIVER LA. Ce serveur ne donne le poids par aucun
    autre moyen — mesure faite, pas supposee :
      - HEAD ne renvoie aucun « Content-Length » (0 sur 250) ;
      - « Range: bytes=0-0 » est IGNORE : il repond 200 et envoie tout le
        fichier, pas 206 avec un « Content-Range ».
    La raison est visible dans les entetes : les images ne sont pas des
    fichiers statiques, elles sortent d un script PHP (Content-Disposition,
    cookie PHPSESSID, Transfer-Encoding: chunked). En « chunked », le poids
    n est connu qu une fois le dernier octet arrive.

    Consequence a retenir pour la suite : ces images sortent aussi en
    « Cache-Control: no-store, no-cache » — aucun cache, aucun CDN ne les
    gardera, et chaque affichage reveille PHP chez l hebergeur d en face."""
    if _lus[0] >= PLAFOND_OCTETS:
        return None, 'plafond'
    req = urllib.request.Request(u, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            n = 0
            while True:
                b = r.read(65536)
                if not b:
                    break
                n += len(b)
            _lus[0] += n
            return n, r.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, type(e).__name__


def moyenne(v):
    return sum(v) / float(len(v)) if v else 0.0


def ecart_type(v):
    if len(v) < 2:
        return 0.0
    m = moyenne(v)
    return (sum((x - m) ** 2 for x in v) / float(len(v) - 1)) ** 0.5


def go(n):
    return '%.2f Go' % (n / 1024.0 / 1024.0 / 1024.0)


def mo(n):
    """Affiche en Ko sous le mega-octet.

    « 0.0 Mo » pour une image de 41 Ko n est pas une mesure, c est un zero.
    L unite doit suivre la grandeur, sinon le tableau ment par arrondi."""
    if n < 1024 * 1024:
        return '%.0f Ko' % (n / 1024.0)
    return '%.1f Mo' % (n / 1024.0 / 1024.0)


def main():
    taille_ech = 250
    for a in sys.argv[1:]:
        if a.isdigit():
            taille_ech = int(a)

    tout, par_fiche = urls()
    uniq = sorted(set(tout))

    if '--liste' in sys.argv:
        with open(SORTIE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(uniq) + '\n')
        print('liste ecrite : %s (%d URL uniques)' % (SORTIE, len(uniq)))
        return

    print('=' * 72)
    print('PARC D IMAGES — CATALOGUE OPS')
    print('=' * 72)
    print('fiches importees ............... %d' % len(par_fiche))
    print('liens d images (total) ......... %d' % len(tout))
    print('liens UNIQUES .................. %d' % len(uniq))
    print('doublons entre fiches .......... %d' % (len(tout) - len(uniq)))
    print('fiches SANS aucune image ....... %d' % sum(1 for x in par_fiche if x == 0))
    print('images par fiche : min %d / moyenne %.1f / max %d'
          % (min(par_fiche), moyenne(par_fiche), max(par_fiche)))
    rep = collections.Counter(par_fiche)
    print('repartition ....................', ', '.join(
        '%d img: %d fiches' % (k, rep[k]) for k in sorted(rep)[:12]))

    hotes = collections.Counter(u.split('/')[2] for u in uniq if '//' in u)
    print('domaines ....................... %s' % ', '.join(
        '%s (%d)' % (h, c) for h, c in hotes.most_common(5)))

    # LES EXTENSIONS. Verification locale, gratuite, et elle a trouve ce que
    # l echantillon reseau n aurait revele qu au hasard : la colonne « Image »
    # ne contient pas que des images. Une video importee comme visuel de fiche
    # produit ne s affiche pas — elle casse la vignette.
    ext = collections.Counter(
        (u.rsplit('.', 1)[1].split('?')[0].lower() if '.' in u.rsplit('/', 1)[-1] else '(aucune)')
        for u in uniq)
    print('extensions ..................... %s' % ', '.join(
        '%s: %d' % (k, v) for k, v in ext.most_common(8)))
    NON_IMAGE = ('mp4', 'mov', 'avi', 'webm', 'pdf', 'zip', 'wmv', 'mkv')
    intrus = [u for u in uniq if u.rsplit('.', 1)[-1].split('?')[0].lower() in NON_IMAGE]
    print('NON-IMAGES dans la colonne ..... %d' % len(intrus))
    if intrus:
        touchees = 0
        with open(IMPORT, encoding='utf-8-sig', newline='') as f:
            for l in csv.DictReader(f):
                us = [x.strip() for x in (l.get('Images') or '').split(',') if x.strip()]
                if not us:
                    continue
                if any(x in intrus for x in us):
                    touchees += 1
                    # Une fiche dont la PREMIERE image est une video n a pas
                    # de vignette de catalogue : c est le cas qui se voit.
        print('  fiches concernees ............ %d' % touchees)
        prem = 0
        with open(IMPORT, encoding='utf-8-sig', newline='') as f:
            for l in csv.DictReader(f):
                us = [x.strip() for x in (l.get('Images') or '').split(',') if x.strip()]
                if us and us[0] in intrus:
                    prem += 1
        print('  dont la VIGNETTE en depend ... %d' % prem)
        for u in intrus[:4]:
            print('    %s' % u)

    # ---------------- 1. recensement COMPLET des .mp4 ----------------
    #
    # Ma premiere passe a tire 250 liens au hasard, trouve 2 morts, et projete
    # « ~167 liens morts sur 20 876 ». Ce chiffre etait faux, et sa fausseté
    # etait previsible : les DEUX morts etaient des .mp4. Une panne concentree
    # dans un sous-ensemble de 214 elements ne se projette pas sur 20 876.
    #
    # Le sous-ensemble est assez petit pour etre teste EN ENTIER. On ne
    # projette donc rien du tout : on compte.
    print()
    print('-' * 72)
    print('LES 214 .mp4 — RECENSEMENT COMPLET (pas un echantillon)')
    print('-' * 72)
    st_mp4 = collections.Counter()
    mp4_vivants = []
    for i, u in enumerate(intrus, 1):
        s, n, t = entete(u)
        st_mp4[s] += 1
        if s == 200:
            mp4_vivants.append(u)
        if i % 25 == 0:
            sys.stdout.write('  %d/%d\r' % (i, len(intrus)))
            sys.stdout.flush()
    print('statuts ........................ %s' % ', '.join(
        '%s: %d' % (k, v) for k, v in st_mp4.most_common()))
    print('.mp4 MORTS ..................... %d / %d' % (
        len(intrus) - st_mp4.get(200, 0), len(intrus)))

    # ---------------- 2. poids, par type ----------------
    #
    # Le poids ne s obtient qu en lisant les octets (voir poids_reel). On
    # echantillonne donc, type par type, parce qu un .mp4 et un .jpg n ont
    # aucune raison de peser pareil et qu une moyenne commune noierait les
    # deux. Volume lu : quelques dizaines de Mo, plafonnes.
    familles = collections.OrderedDict()
    familles['jpg'] = [u for u in uniq if u.lower().endswith('.jpg')]
    familles['png'] = [u for u in uniq if u.lower().endswith('.png')]
    familles['mp4'] = mp4_vivants

    print()
    print('-' * 72)
    print('POIDS MESURE PAR TYPE (lecture reelle des octets, plafond %s)'
          % mo(PLAFOND_OCTETS))
    print('-' * 72)

    total_estime = 0.0
    borne_bas = borne_haut = 0.0
    for nom, pop in familles.items():
        if not pop:
            continue
        r = random.Random(GRAINE + len(nom))
        n_ech = min(taille_ech if nom != 'mp4' else 25, len(pop))
        ech = r.sample(pop, n_ech)
        tailles = []
        for i, u in enumerate(ech, 1):
            n, s = poids_reel(u)
            if n:
                tailles.append(n)
            if i % 10 == 0:
                sys.stdout.write('  %s %d/%d\r' % (nom, i, len(ech)))
                sys.stdout.flush()
        if not tailles:
            print('%s : aucune mesure' % nom)
            continue
        m, sd = moyenne(tailles), ecart_type(tailles)
        err = 1.96 * sd / (len(tailles) ** 0.5)
        sous_total = m * len(pop)
        total_estime += sous_total
        borne_bas += max(0.0, m - err) * len(pop)
        borne_haut += (m + err) * len(pop)
        print('%-4s %6d fichiers | moyenne %9s | mediane %9s | max %9s | ~%s'
              % (nom, len(pop), mo(m), mo(sorted(tailles)[len(tailles) // 2]),
                 mo(max(tailles)), go(sous_total)))
        print('       mesure sur %d fichiers reellement lus' % len(tailles))

    print()
    print('POIDS TOTAL ESTIME ............. %s' % go(total_estime))
    print('  intervalle a 95 %% ............ %s a %s' % (go(borne_bas), go(borne_haut)))
    print('  octets reellement lus ........ %s' % mo(_lus[0]))

    # Le seul chiffre qui interesse l hebergeur : combien de temps et de
    # requetes pour tout rapatrier, fiche par fiche, depuis SON serveur.
    print()
    print('CE QUE CA REPRESENTE POUR UN IMPORT WOOCOMMERCE')
    print('  requetes sortantes ........... %d' % len(uniq))
    print('  a 2 images/seconde ........... %.1f heures' % (len(uniq) / 2.0 / 3600))
    print('  a 5 images/seconde ........... %.1f heures' % (len(uniq) / 5.0 / 3600))
    print('  espace disque necessaire ..... %s (+ les vignettes WordPress)' % go(total_estime))
    # WordPress fabrique par defaut 4 a 5 formats derives par image.
    print('  avec 4 vignettes par image ... ~%s' % go(total_estime * 1.6))


if __name__ == '__main__':
    main()
