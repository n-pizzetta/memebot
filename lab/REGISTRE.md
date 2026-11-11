# Registre des essais

Tout essai y figure, même abandonné (règle 6 de `LAB.md`).

| # | Hypothèse | Version | Statut | Début | Fin | Trades clos | Verdict |
|---|---|---|---|---|---|---|---|
| 001 | Cassure + volume, memecoins survivants | breakout v1 | archivée (bugs d'exécution) | 2026-10-25 | 2026-11-03 | 12 | aucun : échantillon trop petit, défauts corrigés en v2 |
| 002 | Idem, une bougie = un trade, rug ≤ 2 % | breakout v2 | en paper | 2026-11-03 | — | 0 | — |
| 003 | Prime du week-end, actions tokenisées | xstocks_premium v1 | proposée | — | — | — | — |
| 004 | Suivre les setups du compte X vs ETF MSCI World | setups v1 | en paper | 2026-09-30 | — | 0 | verdict prévu en mars 2027 |
| 005 | Signaux fantômes : breakout v2 sans le filtre des disjoncteurs | mesure (rapport), pas de trading | proposée | — | — | — | — |

## Idées en attente (pas encore de fiche)

- **Portage de funding** : acheter le spot, vendre le perpétuel quand le funding est positif
  (risques : plateforme, liquidation de la jambe vendeuse, funding qui s'inverse).
- **Déblocages de tokens** : lire les calendriers de déblocage et mesurer le prix autour.
- **Tickers récidivistes** : deux rugs du même ticker « XTO » en 5 jours. Exclure un ticker
  après un rug ? À mesurer sur le journal avant d'y croire.
