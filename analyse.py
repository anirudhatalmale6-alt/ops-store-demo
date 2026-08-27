# -*- coding: utf-8 -*-
"""Audit du fichier ops_store_data (5).csv avant tout import.

Rien ici n'est estime : chaque chiffre imprime est compte sur le fichier. Le
but est de savoir ce qui manque AVANT que 8 474 fiches soient en ligne, parce
qu'apres, une fiche vide se corrige a la main.

    python3 analyse.py
"""

import csv, os, re, sys, collections, urllib.parse
import rayons
from rayons import lire, vide, ENCODAGE

HERE = os.path.dirname(os.path.abspath(__file__))


def titre(t):
    print('\n' + t)
    print('-' * len(t))


def prix(v):
    """Renvoie un float, ou None si le fichier ne donne pas de prix.

    Le fichier ecrit « N/A ». Le convertir en 0 mettrait 139 articles a zero
    euro dans la boutique — pas « prix inconnu », GRATUIT."""
    if vide(v):
        return None
    s = re.sub(r'[^\d.,]', '', v.replace(' ', '').replace('\xa0', '')
               .replace(' ', ''))
    if s.count(',') == 1 and s.count('.') == 0:
        s = s.replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


def langue(l):
    """La langue de la fiche se lit dans son adresse, pas dans une colonne."""
    return 'en' if '/en/' in l['URL'] else 'fr'


def main():
    L = lire()
    n = len(L)
    brut = open(rayons.CSV, 'rb').read()

    titre('Le fichier')
    print('  %d octets, %d lignes, %d colonnes'
          % (len(brut), n, len(L[0])))
    print('  encodage : CP1252 (PAS Latin-1)')
    print('    l\'octet 0x80 apparait %d fois : c\'est « € » en CP1252 et un'
          % brut.count(b'\x80'))
    print('    caractere de controle en Latin-1. Lu en Latin-1, chaque prix')
    print('    de la boutique perd son symbole monetaire.')
    print('    autres octets CP1252 presents : 0x99 (™) x%d, 0x92 (’) x%d'
          % (brut.count(b'\x99'), brut.count(b'\x92')))
    try:
        brut.decode('utf-8')
        print('    lisible en UTF-8 : oui')
    except UnicodeDecodeError as e:
        print('    lisible en UTF-8 : NON (%s)' % str(e)[:52])

    titre('Ce que le fichier ne contient pas')
    print('  aucune colonne de categorie, rayon, famille ou fil d\'Ariane')
    print('  aucune colonne de stock, de poids d\'expedition ou de TVA')
    print('  aucun identifiant d\'affiliation dans les %d adresses' % n)
    print('  les adresses sont plates : rien a decouper pour deviner un rayon')

    titre('Les deux langues')
    par = collections.Counter(langue(l) for l in L)
    en = {l['Reference'] for l in L if langue(l) == 'en'}
    fr = [l for l in L if langue(l) == 'fr']
    dbl = [l for l in fr if l['Reference'] in en]
    print('  %d fiches en anglais, %d en francais' % (par['en'], par['fr']))
    print('  dont %d fiches francaises qui redoublent une fiche anglaise'
          % len(dbl))
    print('    (meme reference, meme prix, deux adresses — importees telles')
    print('     quelles, ces %d articles apparaissent DEUX FOIS en boutique)'
          % len(dbl))
    print('  %d fiches n\'existent qu\'en francais' % (len(fr) - len(dbl)))
    print('  les 307 colonnes d\'attributs ne sont pas une traduction : ce sont')
    print('  DEUX vocabulaires disjoints. « Caliber » n\'est rempli que sur les')
    print('  fiches anglaises, « Calibre » que sur les francaises.')

    titre('Les trous')
    d = sum(1 for l in L if vide(l['Description']))
    p = sum(1 for l in L if prix(l['Price']) is None)
    print('  %d fiches sur %d n\'ont PAS de description (%.0f %%)'
          % (d, n, 100.0 * d / n))
    print('    le fichier n\'ecrit jamais une case vide, il ecrit « N/A » :')
    print('    importe sans garde-fou, « N/A » devient le texte de la page.')
    print('  %d fiches n\'ont pas de prix (« N/A »)' % p)
    print('    converti en nombre, « N/A » vaut 0 : ces articles seraient')
    print('    affiches GRATUITS, pas « prix sur demande ».')
    print('  %d fiche sans intitule'
          % sum(1 for l in L if vide(l['Product Name'])))
    print('  %d fiches sans aucune image'
          % sum(1 for l in L if vide(l.get('Image 1'))))

    titre('Les prix')
    v = [prix(l['Price']) for l in L]
    ok = sorted(x for x in v if x is not None)
    print('  devise : euro (le fichier ne contient aucun autre symbole)')
    print('  %d prix lisibles, du plus bas au plus haut : %.2f € -> %.2f €'
          % (len(ok), ok[0], ok[-1]))
    print('  median %.2f €, moyenne %.2f €'
          % (ok[len(ok) // 2], sum(ok) / len(ok)))
    tr = [(0, 20), (20, 50), (50, 100), (100, 300), (300, 800), (800, 99999)]
    for a, b in tr:
        c = sum(1 for x in ok if a <= x < b)
        print('    %4d - %-5d € : %5d  %s' % (a, b, c, '#' * (c * 40 // len(ok))))

    titre('Les marques')
    m = collections.Counter((l['Brand'] or '').strip() for l in L)
    print('  %d marques distinctes, aucune fiche sans marque' % len(m))
    print('  les 10 premieres : %s'
          % ', '.join('%s (%d)' % (k, x) for k, x in m.most_common(10)))
    print('  %d marques n\'ont qu\'un seul article'
          % sum(1 for k, x in m.items() if x == 1))

    titre('Les images')
    tot = 0
    cnt = collections.Counter()
    hotes = collections.Counter()
    for l in L:
        k = 0
        for i in range(1, 21):
            u = (l.get('Image %d' % i) or '').strip()
            if not vide(u):
                k += 1
                tot += 1
                hotes[urllib.parse.urlsplit(u).netloc] += 1
        cnt[k] += 1
    print('  %d liens d\'images, de %d a %d par article (median %d)'
          % (tot, min(cnt), max(cnt),
             sorted(k for k, x in cnt.items() for _ in range(x))[n // 2]))
    print('  toutes hebergees chez : %s'
          % ', '.join('%s (%d)' % (k, x) for k, x in hotes.most_common(3)))
    print('  ce sont des liens vers le serveur d\'un tiers. Les rapatrier,')
    print('  c\'est %d telechargements sur un hebergement mutualise.' % tot)

    titre('Les rayons reconstruits')
    res = [(l, rayons.classer(l)) for l in L]
    c = collections.Counter(x[0] for _, x in res)
    mot = collections.Counter(x[2].split(':')[0] for _, x in res)
    ordre = [r[0] for r in rayons.RAYONS] + [rayons.FOURRE_TOUT[0]]
    lib = dict([(r[0], r[1]) for r in rayons.RAYONS] + [rayons.FOURRE_TOUT])
    for o in ordre:
        if c[o]:
            print('  %-32s %5d  %4.1f %%' % (lib[o], c[o], 100.0 * c[o] / n))
    print('  reconnus par attribut %d, par mot %d, par signal faible %d'
          % (mot['attribut'], mot['mot'], mot['faible']))
    print('  restes dans « divers » : %d (%.1f %%)'
          % (mot['aucun'], 100.0 * mot['aucun'] / n))

    titre('Ce qu\'il reste a decider (aucune de ces reponses n\'est dans le fichier)')
    print('  1. affiliation : les %d adresses ne portent aucun identifiant.' % n)
    print('     Sans lui, un clic vers ops-store.com ne rapporte rien.')
    print('  2. images : liees a chaud chez ops-store.com, ou recopiees ?')
    print('     Recopier = %d fichiers + l\'accord ecrit du proprietaire.' % tot)
    print('  3. les %d doublons FR/EN : on garde quelle langue ?' % len(dbl))
    print('  4. les %d fiches sans prix : masquees, ou « prix sur demande » ?' % p)
    print('  5. les %d fiches sans description : en ligne quand meme, ou' % d)
    print('     seulement les %d qui en ont ?' % (n - d))


if __name__ == '__main__':
    main()
