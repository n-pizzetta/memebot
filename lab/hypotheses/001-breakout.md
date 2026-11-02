# 001 — Cassure de plus haut avec volume sur memecoins « survivants »

- **Statut** : archivée le 2026-11-03 (remplacée par v2, voir 002), garde ses positions ouvertes
- **Stratégie / version** : `breakout` v1
- **Auteur** : humain
- **Date** : 2026-10-25

## Hypothèse
Un memecoin Solana qui a survécu 24 h à 7 jours, qui passe les filtres de sécurité et dont la
dernière bougie horaire close casse le plus haut des 24 h précédentes avec un volume ≥ 1,5 ×
la médiane, continue de monter assez souvent pour couvrir des coûts élevés.

## Pourquoi ça pourrait marcher
L'attention sur les memecoins arrive par vagues : une cassure avec volume peut marquer
le début d'une vague.

## Règles
Voir `bot/strategies/breakout.py`, version 1 : stop -15 %, objectif +30 %, sortie forcée à
48 h, 1 % de risque par trade (position max 10 % du capital), 1,5 % de slippage et 0,3 % de
frais par côté.

## Critère d'échec
Après 100 trades clos, espérance par trade ≤ 0 après coûts.

## Référence
Garder du SOL sur la même période.

## Résultats (au 2026-11-03, 12 trades clos, échantillon insuffisant)
- Capital fictif 1 000 $ → 814 $ (-18,6 %), 2 gains sur 12, espérance -15,47 $ par trade.
- Avec ces sorties et ces coûts, gains ≈ +31 % et pertes ≈ -20 % de la position : il faudrait
  gagner environ 4 trades sur 10 pour être à l'équilibre, avant même les rugs.
- **Deux rugs (deux tokens différents, même ticker « XTO ») = -122 $ sur -186 $ de perte
  nette.** Le stop à -15 % est vérifié toutes les 15 min ; un rug passe au travers, donc une
  position de 6,7 % du capital pouvait coûter 6,7 %, pas le 1 % prévu.
- **Bug de ré-entrée** : quand une position se fermait, le même run pouvait la rouvrir sur la
  même bougie (REMUS à 21:07 et 21:45, ███ à 22:15 le 26/10). 3 entrées sur 13.

Ces deux points sont corrigés en v2 (fiche 002). v1 n'est pas modifiée, pour que ses chiffres
restent lisibles.
