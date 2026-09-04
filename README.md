# MFWAM Météo-France — cartes de vagues WordPress

Ce dépôt construit une chaîne directe **Météo-France MFWAM 0,025° → GitHub → WordPress/Avada**. Il publie des cartes interactives des vagues pour la façade maritime française sur une branche `data`, sans intermédiaire tiers (aucune dépendance à un autre site météo).

## Ce que produit le workflow

Première version (v1.0.0) — 4 des 18 paramètres du paquet ouvert SP1 :

- hauteur significative des vagues (`swh`) ;
- hauteur mer du vent (`shww`) ;
- période moyenne des vagues (`mwp`) ;
- période mer du vent (`mpww`).

Grille FRANGP0025 (0,025°, domaine 53N 38N 8W 12E), échéances horaires jusqu'à +48 h (+42 h sur les runs 06/18 UTC), 4 runs par jour (00/06/12/18 UTC). Les 14 autres paramètres du paquet SP1 (direction, houles primaire/secondaire/totale, période de pic, vent, direction du vent) seront ajoutés progressivement, comme pour le module AROME. Benjamin-Feir, hauteur maximale individuelle et période de Hmax ne figurent pas dans le paquet ouvert SP1 et ne peuvent donc pas être publiés pour l'instant.

## Installation du dépôt GitHub

1. Ce dépôt est déjà en place : copiez tout le contenu de ce dossier à sa racine (déjà fait par ce commit).
2. Dans **Settings → Actions → General → Workflow permissions**, choisissez **Read and write permissions**.
3. Lancez **Actions → Mise à jour MFWAM France → Run workflow**.
4. À la fin du premier lancement, vérifiez la présence de la branche `data` et de son fichier `index.json`.

Le workflow est aussi lancé automatiquement 4 fois par jour, 40 min après chaque réseau (00/06/12/18 UTC). Le script compare le run publié et ne reconstruit rien lorsqu'il n'existe pas de nouveau run complet.

Les paquets MFWAM 0,025° utilisés ici sont publics : **aucune clé API Météo-France n'est nécessaire**.

Commande équivalente en local :

```bash
python -m pip install -r requirements.txt
python scripts/update_mfwam_france.py --output-dir build/national
```

## Module WordPress

Le dossier `wordpress/mfwam-meteofrance/` contient le plugin (`[mfwam_meteo]`) à installer sur alertes-meteo.com. Il lit `index.json` et `maps/index.json` depuis la branche `data` de ce dépôt (URL configurable dans Réglages > MFWAM Météo-France).
