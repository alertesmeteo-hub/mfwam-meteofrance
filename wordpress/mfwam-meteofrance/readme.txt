=== MFWAM Météo-France — Cartes de vagues ===
Contributors: alertesmeteo
Tags: meteo, mfwam, vagues, houle, meteofrance, avada
Requires at least: 5.8
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Module de cartes interactives du modèle de vagues MFWAM de Météo-France (façade maritime française, 0,025°).

== Description ==

Le shortcode [mfwam_meteo] affiche une carte interactive des vagues :

* hauteur significative des vagues ;
* hauteur et période de la mer du vent ;
* période moyenne des vagues ;
* échéances horaires jusqu'à +48 h, animation, zoom et légende.

Première version : 4 des 18 paramètres du paquet SP1 (grille FRANGP0025).
Les autres (direction, houles primaire/secondaire/totale, période de pic,
vent, Benjamin-Feir, hauteur max individuelle...) seront ajoutés
progressivement, comme pour le module AROME.

Les données sont lues depuis la branche data du dépôt GitHub configuré dans
Réglages > MFWAM Météo-France.

== Installation ==

1. Téléversez le ZIP dans Extensions > Ajouter une extension.
2. Activez MFWAM Météo-France.
3. Vérifiez l'URL des données dans Réglages > MFWAM Météo-France.
4. Insérez [mfwam_meteo] dans un bloc Avada.

== Changelog ==

= 1.0.0 =
* Première version : 4 cartes MFWAM 0,025° (hauteur significative, hauteur
  et période de la mer du vent, période moyenne des vagues).
