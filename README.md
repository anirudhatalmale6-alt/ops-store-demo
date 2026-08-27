# OPS Store — catalogue de demonstration

Vitrine statique construite a partir de `ops_store_data (5).csv`
(8 474 lignes, 333 colonnes, CP1252).

**Demonstration en ligne :** https://anirudhatalmale6-alt.github.io/ops-store-demo/

## Ce que c'est

Un catalogue d'**affiliation** : chaque vignette renvoie vers la fiche
d'origine sur ops-store.com. Il n'y a ni panier, ni paiement, ni stock —
c'est le fonctionnement normal de ce type de boutique, et c'est aussi ce que
produit le fichier d'import WooCommerce livre a cote (`Type: external`).

## Les chiffres, tous comptes sur le fichier

| | |
|---|---|
| lignes dans le CSV | 8 474 |
| articles apres dedoublonnage | 8 441 |
| doublons FR/EN ecartes | 32 |
| fiche sans intitule ecartee | 1 |
| marques | 532 |
| rayons reconstruits | 20 |
| liens d'images retenus | 20 662 |
| poids du parc d'images | **1,35 Go** (240 fichiers lus ; intervalle a 95 % : 1,15–1,55 Go) |
| liens `.mp4` retires | 214 — **tous morts**, recensement complet 214/214 en 404 |
| articles **sans description** | 6 936 (82 %) |
| articles **sans prix** | 135 |
| prix | 0,50 € a 2 249,90 € (median 39,90 €) |

## Trois choses que le fichier ne dit pas

1. **Aucune categorie.** 333 colonnes, pas une seule qui range l'article, et
   les adresses sont plates. Les 20 rayons sont donc *reconstruits* par regles
   ecrites (`rayons.py`), en trois passes : attributs remplis, puis mots de
   l'intitule en anglais et en francais, puis signaux faibles. 94,3 % des
   articles sont ranges, les 5,7 % restants vont dans « Accessoires divers ».
   Le detail est verifiable ligne par ligne : `python3 rayons.py --tout`.

2. **« N/A » n'est pas une case vide.** Le fichier ecrit litteralement la
   chaine `N/A`. Importee telle quelle, elle devient le texte de 6 936 pages
   produit, et un prix de 0,00 € sur 135 articles — donc *gratuits*, pas
   « prix sur demande ».

3. **Deux langues melangees.** 7 792 fiches anglaises et 682 francaises dans
   le meme fichier, dont 32 qui redoublent une fiche anglaise sous la meme
   reference. Les 307 colonnes d'attributs ne sont pas une traduction : ce
   sont deux vocabulaires disjoints (`Caliber` n'est jamais rempli sur une
   fiche francaise, `Calibre` jamais sur une anglaise).

## Les images (1,35 Go) — `import/ops-images.php`

Deux options, et la difference n'est pas une preference de style.

**a) Les laisser chez OPS.** C'est `import/ops-produits.csv` tel quel. Rien a
faire, aucun octet copie. Mais leurs images sortent d'un script PHP avec
`Cache-Control: no-store` et un cookie de session : elles ne seront mises en
cache nulle part, chaque page vue reveille leur serveur, et le jour ou ils
changent une adresse la vignette disparait chez toi.

**b) Les rapatrier.** `import/ops-images.php` fait ce travail **depuis le
serveur de destination**, par tranches de ~20 s, en reprenant ou il s'arrete.
Il verifie la signature binaire de chaque fichier (une page d'erreur nommee
`.jpg` n'est pas une image), ecrit dans un `.part` puis renomme — un fichier
tronque ne peut donc pas etre pris pour un fichier complet a la reprise. A la
fin il fabrique `ops-produits-local.csv`, dont la colonne `Images` pointe vers
le domaine de destination, et garde le lien d'origine pour toute image qu'il
n'a pas pu recuperer.

Mode d'emploi complet en tete du fichier PHP.

> **Pourquoi les 214 `.mp4` devaient partir.** Ils ne coutaient pas 214
> vignettes, ils coutaient **171 fiches produit**. Dans
> `abstract-wc-product-importer.php`, `get_attachment_id_from_url()` leve une
> Exception quand le fichier ne repond pas ; `set_image_data()` est appele
> *avant* `$object->save()` ; le `catch` renvoie une `WP_Error`. Le produit
> n'est jamais enregistre. Une image manquante fait donc echouer la ligne
> entiere, pas seulement son visuel.

Les visuels appartiennent a OPS-Store : en heberger une copie releve de
l'accord avec eux. Le script execute la decision, il ne la prend pas.

## Reconstruire

```
python3 analyse.py       # l'audit complet du fichier
python3 rayons.py        # la couverture des rayons
python3 build.py         # le CSV WooCommerce + cette demo
python3 images.py        # le parc d'images : poids, liens morts, extensions
python3 tests-ops.py     # 47 controles
python3 tests-images.py  # 24 controles du rapatriement (vrai PHP, vrais fichiers)
```
