# -*- coding: utf-8 -*-
"""Controles du rapatriement d'images (ops-images.php).

Le script PHP tourne chez le client, sur un hebergement mutualise auquel je
n'ai pas acces, et il manipule 20 662 fichiers. Un bug de reprise ou de
renommage ne se verrait pas a l'oeil : il se verrait dans six mois, sur une
fiche produit, sous forme de vignette cassee.

On l'execute donc ICI, pour de vrai — vrai serveur PHP, vraies URL, vrais
octets — sur un echantillon reduit, et on verifie ce qui compte :

  - la cle protege l'acces (sinon c'est un robinet de 1,35 Go ouvert a tous) ;
  - un fichier tronque n'est jamais pris pour un fichier complet ;
  - la reprise ne retelecharge rien ;
  - le CSV local pointe vers le bon domaine et garde le lien d'origine quand
    l'image manque ;
  - le CSV reecrit a toujours le meme nombre de colonnes que l'original.

    python3 tests-images.py
"""

import csv, io, json, os, shutil, subprocess, sys, time
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
IMPORT = os.path.join(HERE, 'import')
BAC = os.path.join(HERE, '.essai-images')
CLE = 'essai12345'
ECHANTILLON = 12

_ok = _ko = 0


def t(nom, cond, detail=''):
    global _ok, _ko
    if cond:
        _ok += 1
        print('  ok   %s' % nom)
    else:
        _ko += 1
        print('  ECHEC %s   %s' % (nom, detail))


def get(url, timeout=120):
    """(statut, corps). Ne leve jamais : « pas encore demarre » est un etat
    attendu pendant l'attente du serveur, pas une erreur de test."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return None, ''


def preparer():
    """Un bac a sable : le PHP, une liste courte, et un CSV reduit aux memes URL."""
    if os.path.isdir(BAC):
        shutil.rmtree(BAC)
    os.makedirs(BAC)

    php = open(os.path.join(IMPORT, 'ops-images.php'), encoding='utf-8').read()
    php = php.replace("const CLE = 'A_CHANGER';", "const CLE = '%s';" % CLE)
    # Tranche courte : le test ne doit pas durer 20 secondes par requete.
    php = php.replace('const SECONDES   = 20;', 'const SECONDES   = 8;')
    open(os.path.join(BAC, 'ops-images.php'), 'w', encoding='utf-8').write(php)

    # On prend les premieres fiches du vrai CSV, et les URL qui vont avec :
    # tester sur des URL inventees ne prouverait rien du comportement reseau.
    lignes, urls = [], []
    with open(os.path.join(IMPORT, 'ops-produits.csv'), encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f)
        entete = rd.fieldnames
        for l in rd:
            u = [x.strip() for x in (l.get('Images') or '').split(',') if x.strip()]
            if not u:
                continue
            lignes.append(l)
            urls.extend(u)
            if len(urls) >= ECHANTILLON:
                break
    urls = urls[:ECHANTILLON]

    with open(os.path.join(BAC, 'ops-produits.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=entete)
        w.writeheader()
        for l in lignes:
            w.writerow(l)

    # Une URL volontairement MORTE en fin de liste : il faut que le script la
    # compte en echec, ne cree aucun fichier, et continue.
    morte = 'https://www.ops-store.com/upload/image/inexistant-p-image-000000-grande.jpg'
    with open(os.path.join(BAC, 'ops-images.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(urls + [morte]) + '\n')
    return urls, entete, morte


def port_libre():
    """Un port que PERSONNE n'occupe, demande au systeme.

    Le port etait ecrit en dur (8899). Sur cette machine, 8899 servait deja un
    WordPress d'un autre projet : « php -S » n'a pas pu s'y attacher, et mes
    controles ont interroge CE site-la, qui a repondu 404 a tout. Trois
    controles « en echec » ne parlaient pas de mon script.

    Un port fixe est une supposition sur l'etat de la machine. On demande."""
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    urls, entete, morte = preparer()
    port = port_libre()
    srv = subprocess.Popen(
        ['php', '-S', '127.0.0.1:%d' % port, '-t', BAC],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = 'http://127.0.0.1:%d/ops-images.php' % port
    try:
        # On attend, puis on VERIFIE que celui qui repond est bien le mien :
        # un 200 ne prouve pas l'identite du serveur.
        pret = False
        for _ in range(60):
            s, b = get(base, timeout=3)
            if 'Cle absente ou incorrecte' in b:
                pret = True
                break
            time.sleep(0.25)
        if not pret:
            print('  ECHEC le serveur PHP de test n a pas demarre sur le port %d' % port)
            return 1
        print('  (serveur PHP de test sur le port %d)' % port)

        print('\nACCES')
        s, b = get(base)
        t('sans cle, le script refuse', 'Cle absente ou incorrecte' in b, b[:120])
        s, b = get(base + '?cle=mauvaise')
        t('avec une mauvaise cle, il refuse aussi', 'Cle absente ou incorrecte' in b)
        s, b = get(base + '?cle=' + CLE)
        t('avec la bonne cle, il travaille', 'Rapatriement des images' in b)

        print('\nTELECHARGEMENT')
        # On relance jusqu a TERMINE, comme le ferait le rechargement auto.
        for i in range(30):
            s, b = get(base + '?cle=' + CLE)
            if 'TERMINE' in b:
                break
        t('la tranche finit par afficher TERMINE', 'TERMINE' in b)

        etat = json.load(open(os.path.join(BAC, 'ops-images-etat.json')))
        t('curseur au bout de la liste (%d)' % (len(urls) + 1),
          etat['curseur'] == len(urls) + 1, json.dumps(etat))
        t('%d images telechargees' % len(urls), etat['ok'] == len(urls), json.dumps(etat))
        t('l URL morte est comptee en echec', etat['echecs'] == 1, json.dumps(etat))

        dossier = os.path.join(BAC, 'images')
        fichiers = sorted(os.listdir(dossier))
        t('%d fichiers sur le disque' % len(urls), len(fichiers) == len(urls), str(len(fichiers)))
        t('aucun fichier .part laisse derriere',
          not [x for x in fichiers if x.endswith('.part')], str(fichiers[:3]))
        t('aucun fichier vide', all(
            os.path.getsize(os.path.join(dossier, x)) > 100 for x in fichiers))

        # Le contenu, pas l extension : c est la seule verification qui
        # distingue une vraie image d une page d erreur nommee .jpg.
        entetes_ok = 0
        for x in fichiers:
            with open(os.path.join(dossier, x), 'rb') as fh:
                sig = fh.read(8)
            if sig[:3] == b'\xff\xd8\xff' or sig == b'\x89PNG\r\n\x1a\n':
                entetes_ok += 1
        t('les %d fichiers sont de vraies images (signature binaire)' % len(urls),
          entetes_ok == len(fichiers), '%d/%d' % (entetes_ok, len(fichiers)))

        t('l image morte n a laisse aucun fichier',
          not os.path.isfile(os.path.join(dossier, os.path.basename(morte))))
        t('le journal d echecs contient l URL morte',
          morte in open(os.path.join(BAC, 'ops-images-echecs.txt'), encoding='utf-8').read())

        print('\nREPRISE')
        # Un fichier TRONQUE doit etre refait, pas considere comme acquis.
        cible = os.path.join(dossier, fichiers[0])
        vrai = os.path.getsize(cible)
        with open(cible, 'wb') as fh:
            fh.write(b'x' * 50)
        os.remove(os.path.join(BAC, 'ops-images-etat.json'))
        for i in range(30):
            s, b = get(base + '?cle=' + CLE)
            if 'TERMINE' in b:
                break
        t('un fichier tronque est retelecharge',
          os.path.getsize(cible) == vrai, '%d attendu %d' % (os.path.getsize(cible), vrai))
        etat2 = json.load(open(os.path.join(BAC, 'ops-images-etat.json')))
        t('les autres ne sont pas retelecharges (%d deja presentes)' % (len(urls) - 1),
          etat2['deja'] == len(urls) - 1, json.dumps(etat2))

        print('\nCSV LOCAL')
        s, b = get(base + '?cle=' + CLE + '&csv=1')
        t('la page CSV repond', 'CSV local fabrique' in b, b[:150])
        chemin = os.path.join(BAC, 'ops-produits-local.csv')
        t('le fichier ops-produits-local.csv existe', os.path.isfile(chemin))

        with open(chemin, encoding='utf-8-sig', newline='') as f:
            rd = csv.DictReader(f)
            cols = rd.fieldnames
            rows = list(rd)
        t('meme nombre de colonnes que l original (%d)' % len(entete),
          cols == entete, str(cols[:4]))
        t('aucune colonne perdue sur les lignes',
          all(len(r) == len(entete) for r in rows), str(len(rows)))

        tous = []
        for r in rows:
            tous += [x.strip() for x in (r.get('Images') or '').split(',') if x.strip()]
        locales = [u for u in tous if '127.0.0.1:%d' % port in u]
        distantes = [u for u in tous if 'ops-store' in u]
        t('les images rapatriees pointent vers le serveur local',
          len(locales) == len(urls), '%d locales sur %d' % (len(locales), len(tous)))
        t('elles pointent vers le sous-dossier images/',
          all('/images/' in u for u in locales), str(locales[:1]))
        t('une image non rapatriee garde son lien d origine',
          len(distantes) == len(tous) - len(urls), '%d distantes' % len(distantes))

        # Le fichier doit s ouvrir dans Excel : BOM en tete.
        with open(chemin, 'rb') as fh:
            t('le CSV commence par le BOM UTF-8', fh.read(3) == b'\xef\xbb\xbf')

        # Et surtout : les URL locales doivent REELLEMENT repondre.
        vivantes = 0
        for u in locales[:6]:
            try:
                with urllib.request.urlopen(u, timeout=10) as r:
                    if r.status == 200 and len(r.read(64)) > 10:
                        vivantes += 1
            except Exception:
                pass
        t('les URL locales du CSV repondent vraiment (%d/6)' % vivantes,
          vivantes == min(6, len(locales)), '%d' % vivantes)

    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()

    print('\n%s\n%d controles — %d ok, %d en echec\n%s'
          % ('=' * 60, _ok + _ko, _ok, _ko, '=' * 60))
    return 1 if _ko else 0


if __name__ == '__main__':
    sys.exit(main())
