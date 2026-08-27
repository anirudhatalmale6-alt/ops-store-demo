<?php
/**
 * OPS — rapatriement des 20 662 images, depuis TON serveur.
 * ---------------------------------------------------------------------------
 *
 * POURQUOI CE FICHIER EXISTE, ET PAS UN SIMPLE IMPORT WOOCOMMERCE.
 *
 * Le parc pese environ 1,5 Go. Deux mesures independantes, qui se recoupent :
 * un tirage aleatoire de 240 fichiers donne 1,35 Go (intervalle a 95 % :
 * 1,15 a 1,55 Go), et un bloc de 740 fichiers reellement rapatries donne
 * 74 Ko par image, soit 1,53 Go. Prevois 3 Go de libre : WordPress fabrique
 * 4 a 5 vignettes derivees par image.
 *
 * Trois choses rendent l'import WooCommerce direct impraticable, et elles
 * sont mesurees, pas supposees :
 *
 *  1. Les images d'ops-store.com ne sont pas des fichiers statiques. Elles
 *     sortent d'un script PHP : entetes « Content-Disposition », cookie
 *     PHPSESSID, « Transfer-Encoding: chunked », et surtout
 *     « Cache-Control: no-store, no-cache ». Aucun cache, aucun CDN ne les
 *     gardera : 20 662 telechargements, c'est 20 662 reveils de PHP chez eux.
 *
 *  2. WooCommerce importe les images DANS la meme requete que le produit. Une
 *     image lente et c'est toute la ligne qui attend ; un lot de 8 441 lignes
 *     tombe en timeout bien avant la fin, et on ne sait pas ou il s'est
 *     arrete.
 *
 *  3. Une image introuvable ne coute pas une vignette, elle coute LA FICHE.
 *     Verifie dans le code de WooCommerce (abstract-wc-product-importer.php) :
 *     get_attachment_id_from_url() leve une Exception quand le fichier ne
 *     repond pas ; set_image_data() est appele AVANT $object->save() ; le
 *     catch renvoie une WP_Error. Le produit n'est jamais enregistre.
 *
 * Ce script separe donc les deux temps : d'abord rapatrier tranquillement les
 * fichiers, par lots, en reprenant ou on s'etait arrete ; ensuite seulement
 * importer le CSV, qui pointera vers TON domaine — donc vers des fichiers
 * locaux, immediats, et qui ne peuvent plus faire echouer une fiche.
 *
 * ---------------------------------------------------------------------------
 * MODE D'EMPLOI
 *
 *  1. Ouvre ce fichier et remplace la valeur de CLE ci-dessous par ce que tu
 *     veux (des lettres et des chiffres). Tant que tu ne l'as pas fait, le
 *     script refuse de demarrer — sans cela n'importe qui tombant sur
 *     l'adresse pourrait lancer 1,35 Go de trafic sur ton hebergement.
 *
 *  2. Depose ces deux fichiers ensemble, par FTP, dans un dossier de ton
 *     site, par exemple  /public_html/ops/  :
 *          ops-images.php
 *          ops-images.txt
 *
 *  3. Ouvre dans ton navigateur :
 *          https://TON-DOMAINE/ops/ops-images.php?cle=TA_CLE
 *
 *     La page travaille par tranches d'environ 20 secondes puis se recharge
 *     toute seule. Tu peux fermer l'onglet quand tu veux et revenir plus
 *     tard : elle reprend exactement ou elle en etait.
 *
 *     DUREE. Mesuree ici sur 1 140 images reelles : environ 1,5 image par
 *     seconde, soit a peu pres 4 heures pour les 20 662. Ce n'est pas une
 *     estimation optimiste arrondie vers le bas — c'est le debit constate,
 *     et il vient d'eux : leurs images sortent d'un script PHP, sans cache.
 *     Ton hebergement peut faire mieux ou moins bien. Comme ca tourne tout
 *     seul et que ca reprend, la duree n'a pas grande importance : lance-le
 *     et oublie-le.
 *
 *  4. Quand elle affiche TERMINE, clique sur « Fabriquer le CSV local ». Elle
 *     ecrit alors  ops-produits-local.csv  a cote — c'est CE fichier que tu
 *     importes dans WooCommerce (Produits > Tous les produits > Importer).
 *
 *  5. Une fois l'import WooCommerce fini, SUPPRIME ops-images.php du serveur.
 *
 * ---------------------------------------------------------------------------
 * Note : les visuels appartiennent a OPS-Store. En heberger une copie chez toi
 * releve de ton accord avec eux — le script ne tranche pas cette question, il
 * l'execute. Si l'accord n'est pas ecrit, la version sans copie (les liens
 * pointant chez eux) reste disponible dans ops-produits.csv.
 */

// ===========================================================================
// A REGLER
// ===========================================================================

const CLE = 'A_CHANGER';          // <= remplace par ta propre cle

const DOSSIER    = 'images';       // sous-dossier ou atterrissent les fichiers
const SECONDES   = 20;             // duree d'une tranche de travail
const TIMEOUT    = 25;             // abandon d'une image trop lente
const ESSAIS     = 2;              // nombre de tentatives par image
const LISTE      = 'ops-images.txt';
const CSV_SOURCE = 'ops-produits.csv';
const CSV_LOCAL  = 'ops-produits-local.csv';
const ETAT       = 'ops-images-etat.json';
const ECHECS     = 'ops-images-echecs.txt';

// ===========================================================================

@set_time_limit(0);
@ini_set('memory_limit', '256M');
ignore_user_abort(false);
header('Content-Type: text/html; charset=utf-8');

$base = __DIR__;
$dest = $base . '/' . DOSSIER;

function stop($msg)
{
    echo '<!doctype html><meta charset="utf-8"><body style="font:15px/1.6 system-ui;'
       . 'max-width:720px;margin:60px auto;padding:0 20px">'
       . '<h2 style="color:#b00">Arret</h2><p>' . htmlspecialchars($msg) . '</p></body>';
    exit;
}

if (CLE === 'A_CHANGER') {
    stop("Ouvre ops-images.php et remplace la valeur de CLE par ta propre cle, "
       . "puis recharge cette page avec ?cle=TA_CLE a la fin de l'adresse.");
}
if (!isset($_GET['cle']) || !hash_equals(CLE, (string) $_GET['cle'])) {
    // hash_equals plutot que « === » : la comparaison ne doit pas etre plus
    // rapide quand les premiers caracteres sont bons.
    stop('Cle absente ou incorrecte. Ajoute ?cle=TA_CLE a la fin de l adresse.');
}
if (!is_file($base . '/' . LISTE)) {
    stop('Fichier ' . LISTE . ' introuvable : depose-le a cote de ops-images.php.');
}
if (!is_dir($dest) && !@mkdir($dest, 0755, true)) {
    stop('Impossible de creer le dossier ' . DOSSIER . ' — verifie les droits.');
}

/** Nom de fichier local d'une URL. Verifie : les 20 662 noms sont uniques. */
function nom_local($url)
{
    $n = basename(parse_url($url, PHP_URL_PATH));
    // On ne « nettoie » pas au hasard : mesure faite, les 20 662 noms ne
    // contiennent que [A-Za-z0-9._-] et font 126 octets au plus. Ce filtre est
    // une ceinture, pas une transformation.
    return preg_replace('/[^A-Za-z0-9._-]/', '_', $n);
}

function lire_liste($chemin)
{
    $out = [];
    $f = fopen($chemin, 'r');
    while (($l = fgets($f)) !== false) {
        $l = trim($l);
        if ($l !== '' && strpos($l, 'http') === 0) {
            $out[] = $l;
        }
    }
    fclose($f);
    return $out;
}

/**
 * Telecharge une URL vers un fichier.
 *
 * Ecriture dans un fichier TEMPORAIRE puis rename() : un rename est atomique
 * sur le meme systeme de fichiers. Sans cela, une coupure au milieu laisse un
 * fichier tronque de la bonne taille apparente, la reprise le voit « deja la »
 * et l'image reste cassee pour toujours. C'est exactement le genre de panne
 * qu'on ne decouvre qu'a l'affichage, des mois plus tard.
 */
function telecharger($url, $chemin)
{
    $tmp = $chemin . '.part';
    for ($essai = 1; $essai <= ESSAIS; $essai++) {
        $ok = false;
        $fh = @fopen($tmp, 'wb');
        if (!$fh) {
            return 'ecriture impossible';
        }
        if (function_exists('curl_init')) {
            $ch = curl_init($url);
            curl_setopt_array($ch, [
                CURLOPT_FILE           => $fh,
                CURLOPT_FOLLOWLOCATION => true,
                CURLOPT_MAXREDIRS      => 5,
                CURLOPT_TIMEOUT        => TIMEOUT,
                CURLOPT_CONNECTTIMEOUT => 10,
                CURLOPT_USERAGENT      => 'Mozilla/5.0 (compatible; migration catalogue)',
                CURLOPT_FAILONERROR    => true,
            ]);
            $ok  = curl_exec($ch);
            $err = curl_error($ch);
            $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
            curl_close($ch);
            fclose($fh);
            if (!$ok) {
                @unlink($tmp);
                if ($essai >= ESSAIS) {
                    return $err !== '' ? $err : ('HTTP ' . $code);
                }
                continue;
            }
        } else {
            fclose($fh);
            $ctx = stream_context_create(['http' => [
                'timeout' => TIMEOUT,
                'header'  => "User-Agent: Mozilla/5.0 (compatible; migration catalogue)\r\n",
            ]]);
            $data = @file_get_contents($url, false, $ctx);
            if ($data === false) {
                if ($essai >= ESSAIS) {
                    return 'telechargement refuse';
                }
                continue;
            }
            file_put_contents($tmp, $data);
        }

        // Un fichier de zero octet est un echec silencieux : il satisfait
        // « le fichier existe » a la reprise et n'affiche rien.
        if (!is_file($tmp) || filesize($tmp) < 100) {
            @unlink($tmp);
            if ($essai >= ESSAIS) {
                return 'fichier vide';
            }
            continue;
        }
        // Verification du contenu, pas de l'extension : le serveur pourrait
        // renvoyer une page d'erreur HTML avec un nom en .jpg.
        $sig = file_get_contents($tmp, false, null, 0, 12);
        $est_image = (substr($sig, 0, 3) === "\xFF\xD8\xFF")                 // jpeg
                  || (substr($sig, 0, 8) === "\x89PNG\r\n\x1a\n")            // png
                  || (substr($sig, 0, 6) === 'GIF87a' || substr($sig, 0, 6) === 'GIF89a')
                  || (substr($sig, 0, 4) === 'RIFF' && substr($sig, 8, 4) === 'WEBP');
        if (!$est_image) {
            @unlink($tmp);
            if ($essai >= ESSAIS) {
                return 'contenu non-image';
            }
            continue;
        }
        if (!@rename($tmp, $chemin)) {
            @unlink($tmp);
            return 'renommage impossible';
        }
        return true;
    }
    return 'echec';
}

// ---------------------------------------------------------------------------
// Fabrication du CSV local
// ---------------------------------------------------------------------------
if (isset($_GET['csv'])) {
    if (!is_file($base . '/' . CSV_SOURCE)) {
        stop('Fichier ' . CSV_SOURCE . ' introuvable : depose-le a cote de ops-images.php.');
    }
    // L'adresse publique du dossier est deduite de l'adresse de CETTE page :
    // le script sait ou il est, inutile de te faire saisir un domaine (et
    // impossible de se tromper de sous-domaine ou d'oublier le https).
    $prefixe = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off' ? 'https' : 'http')
             . '://' . $_SERVER['HTTP_HOST']
             . rtrim(dirname($_SERVER['SCRIPT_NAME']), '/') . '/' . DOSSIER . '/';

    $in  = fopen($base . '/' . CSV_SOURCE, 'r');
    $out = fopen($base . '/' . CSV_LOCAL, 'w');
    fwrite($out, "\xEF\xBB\xBF");           // BOM : Excel lit l'UTF-8 sans lui poser de question
    $entete = fgetcsv($in);
    // Le CSV source commence par un BOM ; on le retire de la premiere colonne.
    if (isset($entete[0])) {
        $entete[0] = preg_replace('/^\xEF\xBB\xBF/', '', $entete[0]);
    }
    $col = array_search('Images', $entete, true);
    if ($col === false) {
        stop('Colonne « Images » absente du CSV.');
    }
    fputcsv($out, $entete);
    $lignes = $remplaces = $manquants = 0;
    while (($r = fgetcsv($in)) !== false) {
        if (count($r) !== count($entete)) {
            continue;
        }
        $urls = array_filter(array_map('trim', explode(',', $r[$col])));
        $neuf = [];
        foreach ($urls as $u) {
            $n = nom_local($u);
            if (is_file($dest . '/' . $n)) {
                $neuf[] = $prefixe . rawurlencode($n);
                $remplaces++;
            } else {
                // Fichier absent : on garde le lien d'origine plutot que de
                // pointer vers un 404 chez toi. Une fiche avec une image
                // distante vaut mieux qu'une fiche qui refuse de s'importer.
                $neuf[] = $u;
                $manquants++;
            }
        }
        $r[$col] = implode(', ', $neuf);
        fputcsv($out, $r);
        $lignes++;
    }
    fclose($in);
    fclose($out);
    echo '<!doctype html><meta charset="utf-8"><body style="font:15px/1.6 system-ui;'
       . 'max-width:760px;margin:60px auto;padding:0 20px">';
    echo '<h2>CSV local fabrique</h2><ul>';
    echo '<li>fichier : <code>' . CSV_LOCAL . '</code></li>';
    echo '<li>lignes : ' . $lignes . '</li>';
    echo '<li>images pointant desormais chez toi : ' . $remplaces . '</li>';
    echo '<li>images restees chez OPS (non rapatriees) : ' . $manquants . '</li>';
    echo '</ul><p>Importe <code>' . CSV_LOCAL . '</code> dans WooCommerce, puis '
       . 'supprime <code>ops-images.php</code> du serveur.</p></body>';
    exit;
}

// ---------------------------------------------------------------------------
// Telechargement par tranches
// ---------------------------------------------------------------------------
$liste = lire_liste($base . '/' . LISTE);
$total = count($liste);

$etat = ['curseur' => 0, 'ok' => 0, 'deja' => 0, 'echecs' => 0, 'octets' => 0];
if (is_file($base . '/' . ETAT)) {
    $j = json_decode(file_get_contents($base . '/' . ETAT), true);
    if (is_array($j)) {
        $etat = array_merge($etat, $j);
    }
}
if (isset($_GET['reset'])) {
    $etat = ['curseur' => 0, 'ok' => 0, 'deja' => 0, 'echecs' => 0, 'octets' => 0];
}

$debut  = microtime(true);
$faits  = 0;
$log    = [];
while ($etat['curseur'] < $total && (microtime(true) - $debut) < SECONDES) {
    $url = $liste[$etat['curseur']];
    $nom = nom_local($url);
    $chemin = $dest . '/' . $nom;
    if (is_file($chemin) && filesize($chemin) > 100) {
        $etat['deja']++;
    } else {
        $r = telecharger($url, $chemin);
        if ($r === true) {
            $etat['ok']++;
            $etat['octets'] += filesize($chemin);
        } else {
            $etat['echecs']++;
            file_put_contents($base . '/' . ECHECS, $url . "\t" . $r . "\n", FILE_APPEND);
            $log[] = $nom . ' — ' . $r;
        }
    }
    $etat['curseur']++;
    $faits++;
}
file_put_contents($base . '/' . ETAT, json_encode($etat));

$fini    = $etat['curseur'] >= $total;
$pct     = $total ? round(100 * $etat['curseur'] / $total, 1) : 0;
$vitesse = $faits / max(0.001, microtime(true) - $debut);
$reste   = $vitesse > 0 ? ($total - $etat['curseur']) / $vitesse : 0;
$url_suite = htmlspecialchars($_SERVER['PHP_SELF']) . '?cle=' . rawurlencode(CLE);

echo '<!doctype html><meta charset="utf-8"><title>Images OPS</title>';
if (!$fini) {
    echo '<meta http-equiv="refresh" content="1;url=' . $url_suite . '">';
}
echo '<body style="font:15px/1.6 system-ui,Segoe UI,Roboto,sans-serif;max-width:760px;'
   . 'margin:50px auto;padding:0 20px;color:#222">';
echo '<h2 style="margin-bottom:4px">Rapatriement des images OPS</h2>';
echo '<p style="color:#666;margin-top:0">Tu peux fermer cette page : elle reprend ou elle s arrete.</p>';
echo '<div style="height:26px;background:#eee;border-radius:13px;overflow:hidden">'
   . '<div style="height:100%;width:' . $pct . '%;background:#2f7d32"></div></div>';
echo '<p style="font-size:22px;margin:14px 0"><b>' . number_format($etat['curseur'], 0, ',', ' ')
   . '</b> / ' . number_format($total, 0, ',', ' ') . '  (' . $pct . ' %)</p>';
echo '<table style="border-collapse:collapse">';
foreach ([
    'telechargees'          => number_format($etat['ok'], 0, ',', ' '),
    'deja presentes'        => number_format($etat['deja'], 0, ',', ' '),
    'echecs'                => number_format($etat['echecs'], 0, ',', ' '),
    'volume recu'           => number_format($etat['octets'] / 1048576, 1, ',', ' ') . ' Mo',
    'vitesse'               => number_format($vitesse, 1, ',', ' ') . ' img/s',
    'temps restant estime'  => $fini ? '—' : gmdate('H:i:s', (int) $reste),
] as $k => $v) {
    echo '<tr><td style="padding:2px 18px 2px 0;color:#666">' . $k . '</td><td><b>' . $v . '</b></td></tr>';
}
echo '</table>';

if ($log) {
    echo '<p style="color:#b00;margin-top:18px">Echecs de cette tranche :</p><ul style="color:#b00">';
    foreach (array_slice($log, 0, 10) as $l) {
        echo '<li>' . htmlspecialchars($l) . '</li>';
    }
    echo '</ul><p style="color:#666">La liste complete est dans <code>' . ECHECS . '</code>.</p>';
}

if ($fini) {
    echo '<h3 style="color:#2f7d32">TERMINE</h3>';
    echo '<p><a href="' . $url_suite . '&amp;csv=1" style="display:inline-block;background:#2f7d32;'
       . 'color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none">'
       . 'Fabriquer le CSV local</a></p>';
    echo '<p style="color:#666">Ensuite : importe <code>' . CSV_LOCAL . '</code> dans WooCommerce, '
       . 'puis supprime <code>ops-images.php</code> du serveur.</p>';
} else {
    echo '<p style="color:#666">La page se recharge toute seule. '
       . '<a href="' . $url_suite . '">Continuer maintenant</a></p>';
}
echo '</body>';
