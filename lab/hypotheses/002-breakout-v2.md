# 002 — Breakout v2 : même signal, une bougie = un trade, rug plafonné à 2 %

- **Statut** : en paper (v2)
- **Stratégie / version** : `breakout` v2
- **Auteur** : Claude, à la demande de Nathan
- **Date** : 2026-11-03

## Hypothèse
Celle de 001, testée sans les deux défauts d'exécution de v1. On ne change **pas** le signal
ni les sorties : on veut savoir si le signal lui-même a un avantage.

## Changements par rapport à v1
1. Une bougie horaire ne peut ouvrir qu'un seul trade par token (`signal_ts`), même si la
   position a été fermée entre-temps.
2. Position plafonnée à 2 % du capital (`MAX_LOSS_ON_TOTAL_FAILURE`) : un rug coûte au plus
   2 %. Conséquence : avec un stop à -15 %, la perte « normale » est d'environ 0,3 % du
   capital. Le P&L en dollars sera petit ; l'indicateur à suivre est **l'espérance en % de
   la position**, donnée par le rapport.

## Critère d'échec
Après 100 trades clos : espérance ≤ 0 % de la position après coûts, **ou** capital fictif
moins bon que garder du SOL sur la même période.

## Référence
Garder du SOL (prix enregistré à chaque run depuis la v2).

## Résultats
À remplir par les revues hebdomadaires.
