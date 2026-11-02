# 003 — Prime du week-end sur les actions tokenisées

- **Statut** : proposée — pas encore codée
- **Stratégie / version** : `xstocks_premium` v1 (collecte seule)
- **Auteur** : Claude, discussion du 2026-11-03
- **Date** : 2026-11-03

## Hypothèse
Le week-end, quand la bourse américaine est fermée, le prix sur DEX d'une action tokenisée
(xStocks sur Solana) s'écarte du dernier cours de clôture. Une partie de cet écart est
excessive (pas justifiée par l'ouverture du lundi) et se referme à l'ouverture.

## Pourquoi ça pourrait marcher
Le week-end, les teneurs de marché portent le risque sans pouvoir se couvrir : ils élargissent
les spreads et la liquidité baisse. Le cas extrême : le token AMC de Robinhood à 18 $ pour une
action à 2,54 $ (septembre 2026).

**Limite connue** : l'arbitrage sans risque (créer ou racheter des tokens contre l'action)
est réservé aux participants autorisés. Sans cet accès, jouer la prime est un pari sur
l'ouverture du lundi, pas un arbitrage. C'est pour ça qu'on commence par mesurer.

## Règles — phase 1 : collecte seule, aucun trade
- Univers : une dizaine d'xStocks liquides (SPYx, NVDAx, TSLAx, AAPLx…) sur GeckoTerminal.
- À chaque run : prix DEX, liquidité du pool, et prix de référence de l'action.
- Source du prix de référence : **à choisir** (API gratuite, accessible depuis GitHub Actions).
- Mesures : prime du vendredi 22 h au lundi 15 h 30 (heure de Paris), et écart entre la prime
  du dimanche soir et le mouvement réel à l'ouverture.

## Critère d'échec (phase 1)
Sur 8 week-ends : si la prime du dimanche ne prédit pas mieux l'ouverture que « zéro », ou si
l'écart moyen est inférieur au coût aller-retour (spread + frais DEX), on archive.

## Référence
Ne rien faire.

## Résultats
—
