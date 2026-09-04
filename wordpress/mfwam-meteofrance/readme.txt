=== MFWAM Météo-France — Cartes de vagues ===
Contributors: alertesmeteo
Tags: meteo, mfwam, vagues, houle, meteofrance, avada
Requires at least: 5.8
Requires PHP: 7.4
Stable tag: 1.4.1
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Module de cartes interactives du modèle de vagues MFWAM de Météo-France (façade maritime française, 0,025°).

== Description ==

Le shortcode [mfwam_meteo] affiche une carte interactive des vagues :

* hauteur significative des vagues ;
* hauteur et période de la mer du vent, période moyenne des vagues ;
* hauteur et période de la houle (totale, primaire, secondaire) ;
* période de pic des vagues ;
* échéances horaires jusqu'à +48 h, animation, zoom et légende.

11 des 18 paramètres du paquet SP1 (grille FRANGP0025). Les directions
(MWD, MDWW, MDPS, MDSS) et le vent (WIND, DWI) seront ajoutés
progressivement. L'indice Benjamin-Feir, la hauteur maximale individuelle
et sa période ne figurent pas dans le paquet ouvert Météo-France SP1 et
ne peuvent donc pas être publiés.

Les données sont lues depuis la branche data du dépôt GitHub configuré dans
Réglages > MFWAM Météo-France.

== Installation ==

1. Téléversez le ZIP dans Extensions > Ajouter une extension.
2. Activez MFWAM Météo-France.
3. Vérifiez l'URL des données dans Réglages > MFWAM Météo-France.
4. Insérez [mfwam_meteo] dans un bloc Avada.

== Changelog ==

= 1.4.1 =
* Correctif : l'info-bulle au survol était coupée près des bords de la carte (débordait hors du cadre). Sa position est maintenant limitée pour rester entièrement visible.

= 1.4.0 =
* Zoom à la molette redevenu direct (sans Ctrl) : la carte capture de nouveau la molette pour zoomer dès que le curseur est dessus.
* Supprimé le message « Hors zone / pas de données » de l'info-bulle : elle disparaît simplement au survol des zones sans donnée.
* Supprimé le bouton chevron ⌄ (menu déjà toujours visible depuis la 1.3.0) : le nom du paramètre affiché est maintenant un simple libellé.
* Supprimé le trait de côte blanc (surcouche vectorielle) affiché sur la carte.

= 1.3.0 =
* Le menu des 11 paramètres (Vent / Houle) est maintenant visible en permanence sous la barre d'outils, au lieu d'être caché derrière le petit chevron ⌄. Le bouton reste disponible pour le replier si besoin, mais ne se referme plus automatiquement après avoir choisi une carte.

= 1.2.3 =
* Correctif : la carte avait `touch-action: none` en permanence (prévu pour le glisser-déposer en zoom), ce qui bloquait aussi le défilement tactile/trackpad de la page dès que le curseur passait dessus, même sans zoomer. Passé à `pan-y` par défaut, `none` uniquement pendant un zoom actif.
* Carte agrandie : hauteur par défaut 900 px (au lieu de 700), plafond porté à 1300 px (attribut `hauteur` du shortcode).

= 1.2.2 =
* Correctif : la molette de la souris était captée par la carte dès que le curseur passait dessus (pour le zoom), bloquant le défilement normal de la page — c'était la vraie cause du « menu pas fixe » signalé : la page ne défilait tout simplement pas tant que le curseur restait sur/près de la carte. Le zoom à la molette nécessite maintenant Ctrl (ou Cmd) ; sans cette touche, la page défile normalement et une info-bulle rappelle le raccourci.

= 1.2.1 =
* Correctif : la barre d'outils ne restait pas fixe en défilant, car un conteneur Avada ancêtre (`overflow: clip`) empêche `position: sticky` de fonctionner. Remplacée par une position fixe pilotée en JavaScript (IntersectionObserver), indépendante de la structure du thème.
* Correctif : l'info-bulle au survol se plaçait n'importe où dès que le zoom dépassait 100 % (mauvais référentiel de positionnement). Repositionnée par rapport au cadre de la carte, pas à l'image zoomée.
* Correctif : l'heure du run et de génération affichait l'heure de Paris étiquetée à tort « UTC » (ex. run 06h UTC affiché « 08:00 UTC »). Le fuseau horaire réel est maintenant indiqué automatiquement.

= 1.2.0 =
* Barre d'outils (paramètre + timeline) collante en haut de la carte pendant le défilement de la page.
* Zoom porté à x8 et résolution native des cartes doublée (2400×2400, contre 1600×1600) : moins de flou en zoomant.
* Info-bulle au survol : valeur reconstruite depuis la couleur du pixel et la légende (aucune grille numérique supplémentaire publiée par le pipeline).

= 1.1.0 =
* 7 nouvelles cartes : hauteur et période de la houle (totale, primaire, secondaire), période de pic des vagues. 11 couches au total sur les 18 du paquet ouvert SP1.
* Indice Benjamin-Feir, hauteur maximale individuelle et période de Hmax non disponibles dans ce paquet Météo-France : aucune donnée inventée.

= 1.0.1 =
* Correctif critique : le message « Chargement de la carte… » restait affiché en permanence au-dessus de la carte, même une fois les données chargées, car la règle CSS `.mfwm-loading { display: flex }` l'emportait sur l'attribut HTML `hidden` posé par le JavaScript. Ajout d'une règle `[hidden] { display: none }` explicite.

= 1.0.0 =
* Première version : 4 cartes MFWAM 0,025° (hauteur significative, hauteur
  et période de la mer du vent, période moyenne des vagues).
