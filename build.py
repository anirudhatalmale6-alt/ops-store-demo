# -*- coding: utf-8 -*-
"""Fabrique les deux livrables de la boutique OPS.

    import/ops-produits.csv   fichier d'import WooCommerce
    demo/index.html           vitrine statique, les 8 474 articles

RIEN N'EST TAPE A LA MAIN. Les rayons viennent de rayons.py, les chiffres du
fichier source. Si le CSV change, on relance et tout suit.

TROIS GARDE-FOUS, ET CHACUN CORRIGE UN DEGAT MESURE SUR LE FICHIER.

1. « N/A » N'EST PAS UNE VALEUR. Le fichier n'ecrit jamais une case vide : il
   ecrit la chaine « N/A ». Importe tel quel, 6 943 fiches sur 8 474 auraient
   « N/A » pour texte de page, et 139 auraient un prix de 0,00 € — donc
   GRATUIT, pas « prix sur demande ».

2. LES DOUBLONS FR/EN. 32 references apparaissent deux fois : la meme fiche en
   anglais sur /en/ et en francais sur ops-store.fr. Importees telles quelles,
   WooCommerce refuse la seconde (UGS deja prise) ou ecrase la premiere selon
   le reglage — dans les deux cas en silence. On tranche ici, par une regle
   ecrite : l'anglais gagne, et a langue egale c'est le .com.

3. LE TYPE DE PRODUIT. Ce sont des produits EXTERNES / AFFILIATION, pas des
   produits simples. La difference n'est pas cosmetique : un produit externe
   n'a ni stock, ni panier, ni paiement, ni expedition — son bouton renvoie
   chez ops-store.com. Importes en « simple », les 8 474 articles seraient
   vendables sur un site qui n'a ni stock ni transporteur.

LES IMAGES RESTENT CHEZ OPS-STORE.COM. 20 971 liens, poids mesure sur un
echantillon de 20 : ~1,8 Go. Je ne rapatrie pas 1,8 Go depuis le serveur d'un
tiers, et un import WooCommerce qui essaie le fait fiche par fiche jusqu'a
tomber en timeout. Le lien est donc pose tel quel — c'est le fonctionnement
normal d'une boutique d'affiliation.

    python3 build.py
"""

import csv, json, os, re, sys, html, collections
import rayons
from rayons import lire, vide, classer

HERE = os.path.dirname(os.path.abspath(__file__))
IMPORT = os.path.join(HERE, 'import')
DEMO = os.path.join(HERE, 'demo')

BOUTIQUE = 'https://www.ops-store.com'


def langue(l):
    return 'en' if '/en/' in l['URL'] else 'fr'


def prix(v):
    if vide(v):
        return None
    s = re.sub(r'[^\d.,]', '', v.replace(' ', '').replace('\xa0', '')
               .replace(' ', ''))
    if s.count(',') == 1 and s.count('.') == 0:
        s = s.replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


def texte(v):
    """Une description absente doit rester ABSENTE, pas devenir « N/A »."""
    return '' if vide(v) else v.strip()


# La colonne « Image » du fournisseur ne contient pas que des images : 214 des
# 21 090 liens sont des .mp4. Ils sont TOUS morts — recensement complet, pas
# echantillon : 214 reponses 404 sur 214 (voir images.py). Deux raisons de les
# retirer, et la seconde est la vraie :
#   1. un .mp4 n est pas une vignette de fiche produit ;
#   2. WooCommerce, sur une image introuvable, INTERROMPT la ligne. Ces 214
#      liens font donc rater 171 fiches — pas 171 vignettes, 171 FICHES.
NON_IMAGE = ('.mp4', '.mov', '.avi', '.webm', '.wmv', '.mkv', '.pdf', '.zip')


def images(l):
    out = []
    for i in range(1, 21):
        u = (l.get('Image %d' % i) or '').strip()
        if not vide(u) and u.startswith('http'):
            if u.split('?')[0].lower().endswith(NON_IMAGE):
                continue
            out.append(u)
    return out


def attributs(l):
    """Les caracteristiques renseignees, dans l'ordre du fichier.

    On saute les 6 colonnes d'identite et les 20 d'images ; tout le reste est
    une caracteristique, anglaise ou francaise selon la fiche. Les deux jeux
    ne se chevauchent jamais : une fiche anglaise ne remplit aucune colonne
    francaise (mesure : 0 sur 7 792)."""
    ign = ('URL', 'Product Name', 'Brand', 'Reference', 'Price', 'Description')
    out = []
    for k, v in l.items():
        if k in ign or k.startswith('Image '):
            continue
        if not vide(v):
            out.append((k, v.strip()))
    return out


# --- lecture et dedoublonnage ---------------------------------------------
def catalogue():
    L = [l for l in lire() if not vide(l.get('Product Name'))]
    par = collections.defaultdict(list)
    for l in L:
        par[l['Reference']].append(l)

    gardes, jetes = [], []
    for ref, grp in par.items():
        if len(grp) == 1:
            gardes.append(grp[0])
            continue
        # anglais d'abord ; a langue egale, le .com plutot que le .fr
        grp = sorted(grp, key=lambda x: (langue(x) != 'en',
                                         '.fr/' in x['URL']))
        gardes.append(grp[0])
        jetes.extend(grp[1:])
    return gardes, jetes


def main():
    gardes, jetes = catalogue()
    os.makedirs(IMPORT, exist_ok=True)
    os.makedirs(DEMO, exist_ok=True)

    lib = dict([(r[0], r[1]) for r in rayons.RAYONS] + [rayons.FOURRE_TOUT])

    # ---------- 1. le fichier d'import WooCommerce -------------------------
    COLS = ['Type', 'SKU', 'Name', 'Published', 'Visibility in catalog',
            'Short description', 'Description', 'Regular price',
            'Categories', 'Images', 'External URL', 'Button text',
            'Attribute 1 name', 'Attribute 1 value(s)', 'Attribute 1 visible',
            'Attribute 1 global', 'Attribute 2 name', 'Attribute 2 value(s)',
            'Attribute 2 visible', 'Attribute 2 global']

    sans_prix = sans_desc = 0
    lignes = []
    fiches = []
    for l in gardes:
        ident, libelle, motif = classer(l)
        p = prix(l['Price'])
        d = texte(l['Description'])
        if p is None:
            sans_prix += 1
        if not d:
            sans_desc += 1
        imgs = images(l)
        att = attributs(l)
        # Les caracteristiques deviennent un seul attribut lisible plutot que
        # 307 colonnes vides : WooCommerce n'affiche pas une colonne absente,
        # mais il cree bien 307 attributs globaux si on les lui donne.
        carac = ' | '.join('%s: %s' % (k, v) for k, v in att[:14])

        lignes.append({
            'Type': 'external',
            'SKU': l['Reference'],
            'Name': l['Product Name'].strip(),
            # Un article sans prix part en BROUILLON. Publie, il afficherait
            # un prix vide sur une page de boutique : le visiteur lit « bug »,
            # pas « nous consulter ».
            'Published': '0' if p is None else '1',
            'Visibility in catalog': 'visible',
            'Short description': '',
            'Description': d,
            'Regular price': '' if p is None else ('%.2f' % p),
            'Categories': libelle,
            'Images': ', '.join(imgs),
            'External URL': l['URL'],
            'Button text': 'Voir sur OPS-Store',
            'Attribute 1 name': 'Marque',
            'Attribute 1 value(s)': (l['Brand'] or '').strip(),
            'Attribute 1 visible': '1',
            'Attribute 1 global': '1',
            'Attribute 2 name': 'Caracteristiques',
            'Attribute 2 value(s)': carac,
            'Attribute 2 visible': '1',
            'Attribute 2 global': '0',
        })

        fiches.append({
            'r': l['Reference'],
            'n': l['Product Name'].strip(),
            'm': (l['Brand'] or '').strip(),
            'p': p,
            'c': ident,
            'i': imgs[0] if imgs else '',
            'u': l['URL'],
            'd': 1 if d else 0,
            'k': len(imgs),
        })

    chemin = os.path.join(IMPORT, 'ops-produits.csv')
    # utf-8-sig : Excel ouvre un CSV sans BOM en Latin-1 et rend « Réplique ».
    with open(chemin, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in lignes:
            w.writerow(r)

    # ---------- 2. la vitrine de demonstration -----------------------------
    fiches.sort(key=lambda x: (x['c'], x['n'].lower()))
    par_rayon = collections.Counter(x['c'] for x in fiches)
    marques = collections.Counter(x['m'] for x in fiches)
    avec_prix = [x['p'] for x in fiches if x['p'] is not None]

    ordre = [r[0] for r in rayons.RAYONS] + [rayons.FOURRE_TOUT[0]]
    rayons_js = [{'id': o, 'l': lib[o], 'n': par_rayon[o]}
                 for o in ordre if par_rayon[o]]

    json.dump({'p': fiches, 'r': rayons_js},
              open(os.path.join(DEMO, 'catalogue.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))

    page = PAGE % {
        'n': len(fiches),
        'nfmt': format(len(fiches), ',d').replace(',', ' '),
        'rayons': len(rayons_js),
        'marques': len(marques),
        'sansdesc': sans_desc,
        'sansprix': sans_prix,
        'jetes': len(jetes),
        'pmin': '%.2f' % min(avec_prix),
        'pmax': '%.2f' % max(avec_prix),
        'css': CSS,
        'js': JS,
    }
    open(os.path.join(DEMO, 'index.html'), 'w', encoding='utf-8').write(page)

    print('import/ops-produits.csv : %d articles (%d en brouillon, sans prix)'
          % (len(lignes), sans_prix))
    print('  %d doublons de reference ecartes' % len(jetes))
    print('  %d articles sans description : la case est laissee VIDE,'
          % sans_desc)
    print('  jamais remplie avec « N/A »')
    print('demo/index.html + catalogue.json : %d articles, %d rayons, %d marques'
          % (len(fiches), len(rayons_js), len(marques)))
    print('  poids du catalogue : %d Ko'
          % (os.path.getsize(os.path.join(DEMO, 'catalogue.json')) // 1024))


CSS = """
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  background:#0f1115;color:#e7e9ee}
a{color:inherit;text-decoration:none}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}
header{background:#14171d;border-bottom:1px solid #232733;position:sticky;top:0;z-index:9}
/* padding:16px 20px et non 16px 0 : « .top » est declare APRES « .wrap »,
   a specificite egale il gagne, et le padding lateral de .wrap disparait.
   Invisible en 1280 (la .wrap est deja plus etroite que l'ecran), flagrant
   en 390 ou le logo se collait au bord. */
.top{display:flex;align-items:center;gap:16px;padding:16px 20px}
.logo{font-weight:800;font-size:20px;letter-spacing:.5px}
.logo b{color:#c8ff3d}
.tag{font-size:12px;color:#8b93a5;border-left:1px solid #2b3040;padding-left:14px}
.stats{margin-left:auto;font-size:12.5px;color:#8b93a5}
.stats b{color:#e7e9ee}
.bar{display:flex;flex-wrap:wrap;gap:10px;padding:0 20px 16px}
input,select{background:#1a1e26;border:1px solid #2b3040;color:#e7e9ee;
  border-radius:8px;padding:9px 12px;font-size:14px;font-family:inherit}
input:focus,select:focus{outline:none;border-color:#c8ff3d}
#q{flex:1;min-width:220px}
.note{background:#191d25;border:1px solid #2b3040;border-left:3px solid #c8ff3d;
  border-radius:8px;padding:12px 16px;margin:16px 0;font-size:13px;color:#a9b1c3}
.note b{color:#e7e9ee}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));
  padding:8px 0 40px}
.card{background:#161a21;border:1px solid #232733;border-radius:10px;overflow:hidden;
  display:flex;flex-direction:column;transition:border-color .15s}
.card:hover{border-color:#3a4256}
.ph{aspect-ratio:1/1;background:#fff;display:flex;align-items:center;justify-content:center}
.ph img{width:100%;height:100%;object-fit:contain}
.body{padding:11px 12px 13px;display:flex;flex-direction:column;gap:6px;flex:1}
.br{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#8b93a5}
.nm{font-size:13px;line-height:1.35;flex:1}
.ft{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:4px}
.pr{font-weight:700;font-size:15px;color:#c8ff3d}
.pr.non{color:#8b93a5;font-weight:500;font-size:12px}
.go{font-size:11px;color:#8b93a5;border:1px solid #2b3040;border-radius:6px;padding:4px 8px}
.card:hover .go{border-color:#c8ff3d;color:#c8ff3d}
.more{display:block;margin:0 auto 50px;background:#1a1e26;border:1px solid #2b3040;
  color:#e7e9ee;border-radius:8px;padding:11px 26px;font-size:14px;cursor:pointer}
.more:hover{border-color:#c8ff3d}
.empty{padding:60px 0;text-align:center;color:#8b93a5}
footer{border-top:1px solid #232733;padding:22px 0 40px;font-size:12px;color:#6d7488}
@media(max-width:640px){.stats{width:100%;margin:6px 0 0}.top{flex-wrap:wrap}}
"""

JS = """
var D=null,VU=0,PAS=60;
fetch('catalogue.json').then(function(r){return r.json()}).then(function(j){
  D=j;
  var s=document.getElementById('cat');
  j.r.forEach(function(r){
    var o=document.createElement('option');o.value=r.id;o.textContent=r.l+' ('+r.n+')';
    s.appendChild(o);
  });
  var m={};j.p.forEach(function(p){m[p.m]=(m[p.m]||0)+1});
  var sm=document.getElementById('marque');
  Object.keys(m).sort().forEach(function(k){
    var o=document.createElement('option');o.value=k;o.textContent=k+' ('+m[k]+')';
    sm.appendChild(o);
  });
  ['q','cat','marque','tri','pmax'].forEach(function(id){
    var e=document.getElementById(id);
    e.addEventListener(e.tagName==='INPUT'?'input':'change',function(){VU=0;rendre()});
  });
  document.getElementById('plus').addEventListener('click',function(){rendre(true)});
  rendre();
});

function filtrer(){
  var q=document.getElementById('q').value.trim().toLowerCase(),
      c=document.getElementById('cat').value,
      m=document.getElementById('marque').value,
      pm=parseFloat(document.getElementById('pmax').value),
      t=document.getElementById('tri').value;
  var out=D.p.filter(function(p){
    if(c&&p.c!==c)return false;
    if(m&&p.m!==m)return false;
    // Un article sans prix n'est pas un article a 0 €. Un plafond de prix ne
    // doit donc pas le faire disparaitre en silence : il reste visible et
    // porte « prix non communique ».
    if(pm&&p.p!==null&&p.p>pm)return false;
    if(q&&(p.n+' '+p.m+' '+p.r).toLowerCase().indexOf(q)<0)return false;
    return true;
  });
  if(t==='px')out.sort(function(a,b){return (a.p===null)-(b.p===null)||a.p-b.p});
  else if(t==='pxd')out.sort(function(a,b){return (a.p===null)-(b.p===null)||b.p-a.p});
  else out.sort(function(a,b){return a.n.toLowerCase()<b.n.toLowerCase()?-1:1});
  return out;
}

function rendre(suite){
  var l=filtrer(),g=document.getElementById('grid');
  if(!suite){g.innerHTML='';VU=0}
  var fin=Math.min(VU+PAS,l.length),h='';
  for(var i=VU;i<fin;i++){
    var p=l[i];
    h+='<a class="card" href="'+p.u+'" target="_blank" rel="noopener nofollow">'
      +'<div class="ph">'+(p.i?'<img loading="lazy" src="'+p.i+'" alt="">':'')+'</div>'
      +'<div class="body"><div class="br">'+esc(p.m)+'</div>'
      +'<div class="nm">'+esc(p.n)+'</div><div class="ft">'
      +(p.p===null?'<span class="pr non">prix non communique</span>'
                  :'<span class="pr">'+p.p.toFixed(2).replace('.',',')+' &euro;</span>')
      +'<span class="go">Voir &rarr;</span></div></div></a>';
  }
  g.insertAdjacentHTML('beforeend',h);
  VU=fin;
  document.getElementById('vu').textContent=l.length;
  document.getElementById('plus').style.display=VU<l.length?'block':'none';
  document.getElementById('vide').style.display=l.length?'none':'block';
}

function esc(s){return String(s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
"""

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>OPS Store &middot; catalogue de demonstration</title>
<style>%(css)s</style>
<header>
  <div class="wrap top">
    <div class="logo">OPS<b>.</b>STORE</div>
    <div class="tag">catalogue de demonstration &mdash; affiliation</div>
    <div class="stats"><b>%(nfmt)s</b> articles &middot; <b>%(rayons)d</b> rayons
      &middot; <b>%(marques)d</b> marques &middot; %(pmin)s &euro; &rarr; %(pmax)s &euro;</div>
  </div>
  <div class="wrap bar">
    <input id="q" type="search" placeholder="Chercher un article, une marque, une reference&hellip;">
    <select id="cat"><option value="">Tous les rayons</option></select>
    <select id="marque"><option value="">Toutes les marques</option></select>
    <input id="pmax" type="number" min="0" step="10" placeholder="Prix max &euro;" style="width:120px">
    <select id="tri">
      <option value="nom">Tri : nom</option>
      <option value="px">Tri : prix croissant</option>
      <option value="pxd">Tri : prix decroissant</option>
    </select>
  </div>
</header>
<div class="wrap">
  <div class="note">
    <b>Demonstration.</b> Les %(nfmt)s articles viennent du fichier
    ops_store_data (5).csv, sans retouche. Les rayons n'existent pas dans le
    fichier : ils sont reconstruits par regles (rayons.py) et le detail est
    verifiable ligne par ligne. Chaque vignette renvoie vers ops-store.com &mdash;
    c'est un catalogue d'affiliation, il n'y a ni panier ni paiement ici.
    <br><b>Ce que le fichier ne donne pas :</b> %(sansdesc)d articles n'ont
    aucune description, %(sansprix)d n'ont pas de prix (affiches
    &laquo;&nbsp;prix non communique&nbsp;&raquo;, jamais 0 &euro;), et
    %(jetes)d doublons FR/EN ont ete ecartes.
    Les images restent chez ops-store.com : 20 971 fichiers, ~1,8 Go mesures.
  </div>
  <div style="font-size:13px;color:#8b93a5;padding:4px 0 10px">
    <b id="vu" style="color:#e7e9ee">0</b> articles affiches
  </div>
  <div class="grid" id="grid"></div>
  <div class="empty" id="vide" style="display:none">Aucun article ne correspond.</div>
  <button class="more" id="plus" style="display:none">Afficher la suite</button>
</div>
<footer><div class="wrap">
  Demonstration technique construite pour JNCORP. Les marques, visuels et
  fiches appartiennent a leurs proprietaires ; les liens pointent vers la
  boutique d'origine.
</div></footer>
<script>%(js)s</script>
"""

if __name__ == '__main__':
    main()
