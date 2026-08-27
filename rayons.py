# -*- coding: utf-8 -*-
"""Classe les 8 474 articles du fichier OPS dans des rayons.

POURQUOI CE FICHIER EXISTE. Le CSV n'a AUCUNE colonne de categorie. Ni rayon,
ni famille, ni fil d'Ariane : 333 colonnes et pas une seule qui dise ce qu'est
l'article. Les adresses non plus ne l'indiquent pas — elles sont plates
(/en/<intitule>-a30090.html), il n'y a rien a decouper.

Sans rayon, une boutique de 8 474 references n'a pas de menu, pas de page de
famille, pas de filtre : juste une liste. On les reconstruit donc, et de la
seule maniere honnete quand la donnee manque : par regles ECRITES, relues, et
dont le resultat s'imprime EN ENTIER pour etre verifie a l'oeil.

DEUX SIGNAUX, DANS CET ORDRE.
1. Les colonnes d'attributs REMPLIES. Certaines ne mentent pas : un article
   qui renseigne « Caliber » et « Shooting mode » est une replique ; un
   « Magnification » + « Reticle » est une optique. Peu de colonnes sont aussi
   franches, mais celles-la tranchent seules.
2. Les mots de l'intitule, en anglais ET en francais — 682 fiches sur 8 474
   sont redigees en francais (voir analyse.py), donc un dictionnaire anglais
   seul en laisserait 8 % de cote sans le dire.

La regle qui gagne est la PREMIERE qui matche, l'ordre du tableau RAYONS est
donc significatif : les cas etroits (batteries, billes) passent avant les cas
larges (accessoires), sinon « chargeur de batterie » tombe dans « chargeurs ».

TROIS PASSES, ET LA TROISIEME EXISTE POUR UNE RAISON PRECISE. Beaucoup de
repliques ne se nomment que par leur modele : « HX2002 Full Black ARMORER
WORKS Gas », « M9A1 Stainless Tokyo Marui Gas ». Le seul mot exploitable est
« Gas » ou un nom de modele — signaux trop faibles pour etre lus tot, car
« Glock » designe aussi bien la replique que le holster ou le chargeur qui vont
avec. Ils ne sont donc consultes qu'en DERNIER, sur ce que rien d'autre n'a su
nommer. Fait dans l'autre sens, la premiere version rangeait « Holster for
Glock 17 » dans les repliques.

    python3 rayons.py            -> rapport de couverture
    python3 rayons.py --tout     -> imprime les 8 474 lignes classees
    python3 rayons.py --reste    -> imprime UNIQUEMENT les non classes
"""

import csv, os, re, sys, unicodedata, collections

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, '..', 'ops_store_data (5).csv')

# Le fichier est en CP1252, PAS en Latin-1. La difference n'est pas theorique :
# l'octet 0x80 vaut « € » en CP1252 et un caractere de controle en Latin-1. Il
# apparait 8 335 fois, une par prix. Lu en Latin-1, chaque prix de la boutique
# se termine par un caractere invisible au lieu du symbole monetaire.
ENCODAGE = 'cp1252'


def sansaccent(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn').lower()


def vide(v):
    """Le fichier n'ecrit jamais une case vide : il ecrit « N/A »."""
    return (v or '').strip().upper() in ('', 'N/A', 'NA', '-')


def lire():
    with open(CSV, encoding=ENCODAGE, newline='') as f:
        return list(csv.DictReader(f))


# --- les rayons ------------------------------------------------------------
# (identifiant, libelle, attributs qui suffisent, mots de l'intitule)
# Les mots sont cherches sans accent et sans casse, entoures de non-lettres.
RAYONS = [
    ('billes', 'Billes et gaz',
     ['Tracante', 'Siliconized', 'Silicone'],
     ['bbs', 'bb', 'billes', 'bille', 'grammage', 'green gas', 'gaz',
      'co2', 'capsule', 'propane', 'silicone']),

    ('batteries', 'Batteries et chargeurs',
     ['Battery power', 'Unloading capacity', 'Compatible batteries',
      'Load current', 'Output voltage', 'LCD display'],
     ['lipo', 'life', 'nimh', 'batterie', 'battery', 'accu', 'chargeur de batterie',
      'battery charger', 'balance charger', 'powerbank']),

    ('grenades', 'Grenades et pyrotechnie',
     ['Grenade type', 'Type de grenade', 'Ignition', 'Allumage'],
     ['grenade', 'fumigene', 'smoke', 'thunder', 'pyro', 'detonateur',
      'mine', 'flashbang']),

    ('optiques', 'Optiques et viseurs',
     ['Magnification', 'Reticle', 'Reticule', 'Parallax setting',
      'Optical diameter', 'Grossissement', 'Night vision detection distance',
      'IR wavelength', 'Eye relief', 'Diopter adjustment'],
     ['scope', 'lunette', 'red dot', 'point rouge', 'holographic', 'holographique',
      'viseur', 'sight', 'reflex', 'magnifier', 'monoculaire', 'monocular',
      'jumelle', 'binocular', 'thermique', 'thermal', 'vision nocturne',
      'night vision', 'telemetre', 'rangefinder', 'reticle']),

    ('lampes', 'Lampes et lasers',
     ['Maximum range', 'Colour temperature', 'Head diameter',
      'Portee Maximale', 'Diametre tete', 'Led', 'Maximum power'],
     ['lampe', 'flashlight', 'torch', 'torche', 'laser', 'illuminateur',
      'illuminator', 'strobe', 'peq', 'dbal', 'm300', 'm600', 'surefire']),

    ('radios', 'Radios et communication',
     ['Frequency range', 'Channels', 'Canaux', 'Transmitter power',
      'Sound reduction', 'Reduction des sons', 'Micro'],
     ['radio', 'talkie', 'ptt', 'headset', 'casque audio', 'oreillette',
      'earmor', 'comtac', 'antenne', 'antenna', 'intercom']),

    ('internes', 'Pieces internes',
     ['Gearbox Version', 'Canon internal model', 'Internal barrel diameter',
      'Quick spring change', 'Motor shaft', 'Integrated mosfet', 'Gears',
      'Axis type', "Type d'axe", 'Modele Canon interne', 'RPM',
      'Diameter Hub Outer Barrel', 'Hub Nozzle diameter', 'FCU voltage'],
     ['gearbox', 'nozzle', 'piston', 'cylindre', 'cylinder', 'joint hop',
      'hop up', 'hop-up', 'bucking', 'canon de precision', 'precision barrel',
      'inner barrel', 'canon interne', 'ressort', 'spring guide', 'moteur',
      'motor', 'mosfet', 'gachette', 'trigger', 'engrenage', 'gear set',
      'pignon', 'bearing', 'roulement', 'shim', 'tappet', 'sector',
      'fcu', 'regulateur', 'regulator', 'valve', 'blowback unit',
      'switch', 'culasse', 'bolt', 'cablage', 'wiring', 'gate titan',
      'aster', 'perun']),

    ('chargeurs', 'Chargeurs et alimentation',
     ['Capacity', 'Capacite', 'Cartridges', 'Cartridge slot',
      'Feeder loader diameter', 'Feeder loader length'],
     ['chargeur', 'magazine', 'mag ', 'mid-cap', 'midcap', 'hi-cap', 'hicap',
      'low-cap', 'lowcap', 'drum', 'speed loader', 'speedloader', 'shell',
      'douille', 'cartouche']),

    ('repliques', 'Repliques',
     ['Caliber', 'Calibre', 'Propulsion', 'Shooting mode', 'Mode de tir',
      'Gas location', 'Emplacement gaz', 'Blowback', 'Energy (0.20g BBs)',
      'Energie (Billes 0.20g)', 'Number of guns', 'Firing rate'],
     ['replique', 'replica', 'aeg', 'gbbr', 'gbb', 'aep', 'hpa', 'sniper',
      'fusil', 'rifle', 'pistolet', 'pistol', 'revolver', 'shotgun',
      'fusil a pompe', 'carabine', 'smg', 'dmr', 'lanceur', 'launcher']),

    ('protection', 'Protection et masques',
     ['Protection standards', 'UVA protection', 'UVB protection', 'Glass',
      'Frame color', 'Standards', 'Certification', 'Certifications'],
     ['masque', 'mask', 'lunette de protection', 'goggle', 'protection',
      'genouillere', 'kneepad', 'coudiere', 'elbow', 'plaque', 'plate',
      'gilet pare', 'balistique', 'ballistic', 'mesh']),

    ('casques', 'Casques et accessoires de tete',
     ['Side rails', 'NVG mounting'],
     ['casque', 'helmet', 'fast helmet', 'bump', 'rail casque', 'shroud',
      'contre poids', 'counterweight', 'cagoule', 'balaclava', 'chapeau',
      'boonie', 'casquette', 'cap ']),

    ('vetements', 'Vetements et chaussures',
     ['Available sizes', 'External composition', 'Internal composition',
      'Washing', 'Leg length', 'Longueur de jambe', 'Sole', 'Semelle',
      'Lining', 'Lacing', 'Lacage', 'Washing precautions',
      'Precautions de lavage'],
     ['pantalon', 'pants', 'veste', 'jacket', 'combat shirt', 'chemise',
      'tee shirt', 't-shirt', 'sweat', 'hoodie', 'chaussure', 'boots',
      'rangers', 'gant', 'gloves', 'ceinture', 'belt', 'uniforme',
      'uniform', 'bdu', 'short', 'parka', 'softshell', 'ghillie']),

    ('gilets', 'Gilets, sacs et portage',
     ['Soft system', 'Systeme Molle', 'Soft fixture', 'Volume',
      'External dimensions', 'Internal dimensions',
      'Interior compartment dimensions', 'Foam', 'Mousse'],
     ['gilet', 'vest', 'plate carrier', 'chest rig', 'sac', 'backpack',
      'bag', 'sacoche', 'pouch', 'poche', 'holster', 'etui', 'dump',
      'baudrier', 'harnais', 'harness', 'valise', 'mallette', 'housse',
      'strap', 'webbing', 'bandouliere',
      'molle', 'porte chargeur', 'mag pouch']),

    ('rails', 'Rails, poignees et crosses',
     ['Buffer tube diameter', 'Diametre de tube', 'Integrated bipod',
      'Bipied integre', 'Contracted length'],
     ['rail', 'picatinny', 'keymod', 'm-lok', 'mlok', 'garde main',
      'handguard', 'rail system', 'poignee', 'grip', 'foregrip', 'crosse',
      'stock', 'buffer tube', 'bipied', 'bipod', 'sangle', 'sling',
      'adaptateur', 'adapter', 'montage', 'mount', 'mounting', 'embase',
      'riser', 'anneau', 'anneau de montage', 'collier', 'trepied',
      'tripod', 'qd lever', 'levier']),

    ('silencieux', 'Silencieux et cache-flamme',
     ['No output screw', 'Pas de vis de sortie'],
     ['silencieux', 'silencer', 'suppressor', 'cache flamme', 'flash hider',
      'traceur', 'tracer', 'frein de bouche', 'muzzle', 'compensateur']),

    ('entretien', 'Entretien et outillage',
     ['Paint type', 'Maximum exposure temperature', 'Refillable'],
     ['huile', 'graisse', 'grease', 'nettoyage', 'cleaning', 'outil', 'tool',
      'cle ', 'wrench', 'tournevis', 'screwdriver', 'peinture', 'paint',
      'bombe', 'spray', 'colle', 'ruban', 'tape', 'chiffon', 'kit outil',
      'etabli', 'vise', 'etau']),

    ('cibles', 'Cibles et entrainement',
     ['LED panel dimensions', 'Target dimensions', 'Target weights',
      'Number of game modes'],
     ['cible', 'target', 'porte cible', 'backstop', 'chrono', 'chronograph',
      'test bench', 'banc de test']),

    ('camera', 'Cameras et electronique',
     ['Video resolutions', 'Video format', 'Memory card', 'WiFi connectivity',
      'Mobile application', 'Sensor', 'TV output'],
     ['camera', 'gopro', 'action cam', 'enregistreur', 'dashcam']),

    ('patchs', 'Patchs et identification',
     [],
     ['patch', 'ecusson', 'drapeau', 'flag', 'velcro', 'brassard', 'armband',
      'marqueur', 'name tape', 'sticker', 'autocollant', 'porte cle',
      'keychain', 'pin\'s', 'medaille']),
]

FOURRE_TOUT = ('accessoires', 'Accessoires divers')

# --- 3e passe : signaux faibles -------------------------------------------
# Ces mots ne sont PAS discriminants isolement — « Glock » qualifie autant la
# replique que le holster ou le chargeur. Ils ne sont donc lus qu'apres que
# toutes les regles fermes ont echoue.
FAIBLES = {
    'repliques': ['gas', 'gaz', 'spring', 'co2', 'next gen', 'hi capa',
                  'hi-capa', 'hicapa', 'glock', '1911', 'm4a1', 'm4',
                  'ak47', 'ak74', 'akm', 'mp5', 'mp7', 'mp9', 'scar',
                  'm14', 'm16', 'g17', 'g18', 'g19', 'g45', 'm9a1', 'p226',
                  'p320', 'vsr', 'aap01', 'aap-01', 'deagle', 'desert eagle',
                  'mauser', 'colt', 'beretta', 'fabarm', 'lance grenades',
                  'lance grenade', 'grenade launcher', 'famas', 'sig',
                  'uzi', 'thompson', 'garand', 'kar98', 'mosin', 'ump'],
    'optiques': ['killflash', 'kill flash', 'lens protector',
                 'protection lentille', 'protege lentille', 'lentille',
                 'rmr', 'acog', 'eotech', 'aimpoint'],
    'silencieux': ['muffler', 'compensator', 'compensateur', 'ccw',
                   'outer barrel', 'canon externe', 'muzzle brake'],
    'rails': ['turntable', 'interface', 'plateau', 'plate mount'],
}


def _regex(mots):
    """Mot entier, sans accent, sans casse, PLURIEL TOLERE.

    Le « s? » n'est pas cosmetique : sans lui, « target » ne reconnaissait pas
    « targets » et 19 cibles finissaient dans le fourre-tout. Le mot entier
    reste exige des deux cotes, donc « gas » ne matche toujours pas
    « gasket »."""
    if not mots:
        return None
    parts = [re.escape(sansaccent(m).strip()) for m in mots]
    return re.compile(r'(?<![a-z0-9])(?:%s)s?(?![a-z0-9])' % '|'.join(parts))


REGEX = {r[0]: _regex(r[3]) for r in RAYONS}
REGEX_FAIBLE = {k: _regex(v) for k, v in FAIBLES.items()}
LIBELLE = dict((r[0], r[1]) for r in RAYONS)


def classer(ligne):
    """Renvoie (identifiant, libelle, motif) — motif dit POURQUOI."""
    nom = sansaccent(ligne.get('Product Name') or '')
    for ident, libelle, attrs, _ in RAYONS:
        for a in attrs:
            if not vide(ligne.get(a)):
                return ident, libelle, 'attribut:' + a
    for ident, libelle, _, _ in RAYONS:
        rx = REGEX[ident]
        if rx:
            m = rx.search(nom)
            if m:
                return ident, libelle, 'mot:' + m.group(0)
    for ident, _, _, _ in RAYONS:
        rx = REGEX_FAIBLE.get(ident)
        if rx:
            m = rx.search(nom)
            if m:
                return ident, LIBELLE[ident], 'faible:' + m.group(0)
    return FOURRE_TOUT[0], FOURRE_TOUT[1], 'aucun'


def main():
    lignes = lire()
    res = [(l, classer(l)) for l in lignes]
    par = collections.Counter(c[0] for _, c in res)
    motif = collections.Counter(c[2].split(':')[0] for _, c in res)

    if '--tout' in sys.argv:
        for l, c in res:
            print('%-12s %-9s %s' % (c[0], c[2][:9], (l['Product Name'] or '')[:78]))
        return
    if '--reste' in sys.argv:
        for l, c in res:
            if c[0] == FOURRE_TOUT[0]:
                print('%-9s %s' % ((l['Brand'] or '')[:9], (l['Product Name'] or '')[:88]))
        return

    ordre = [r[0] for r in RAYONS] + [FOURRE_TOUT[0]]
    lib = dict([(r[0], r[1]) for r in RAYONS] + [FOURRE_TOUT])
    print('%d articles, %d rayons\n' % (len(res), len([o for o in ordre if par[o]])))
    for o in ordre:
        if par[o]:
            print('  %-13s %-32s %5d  %4.1f %%'
                  % (o, lib[o], par[o], 100.0 * par[o] / len(res)))
    print('\nreconnu par attribut : %d, par mot : %d, par signal faible : %d,'
          '\nnon classe : %d (%.1f %%)'
          % (motif['attribut'], motif['mot'], motif['faible'], motif['aucun'],
             100.0 * motif['aucun'] / len(res)))


if __name__ == '__main__':
    main()
