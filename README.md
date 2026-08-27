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
| liens d'images | 20 971 (~1,8 Go, mesure sur 20 echantillons) |
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

## Reconstruire

```
python3 analyse.py    # l'audit complet du fichier
python3 rayons.py     # la couverture des rayons
python3 build.py      # le CSV WooCommerce + cette demo
```

Les images ne sont pas recopiees : elles restent chez ops-store.com.
