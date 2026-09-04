=== MFWAM Météo-France — Cartes de vagues ===
Contributors: alertesmeteo
Tags: meteo, mfwam, vagues, houle, meteofrance, avada
Requires at least: 5.8
Requires PHP: 7.4
Stable tag: 1.2.0
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
