# 004 — Suivre les setups du compte X fait-il mieux que l'ETF MSCI World ?

- **Statut** : en paper (v1)
- **Stratégie / version** : `setups` v1
- **Auteur** : Nathan (paper trades depuis le 30/09/2026), intégré au labo par Claude
- **Date** : 2026-11-03

## Hypothèse
Prendre les setups techniques publiés par le compte X suivi, avec leurs stops et objectifs
sur clôture hebdomadaire, rapporte plus que le simple ETF MSCI World sur les mêmes périodes.

## Pourquoi ça pourrait marcher
L'auteur sélectionne des configurations (double bottom, retour sur support…) et coupe vite
les perdants. Ce qui reste à prouver : que cette sélection bat le marché une fois les frais
payés, et pas seulement sur les exemples qu'on retient.

## Règles
- Chaque setup pris est **une ligne de `lab/setups.csv`**, ajoutée le jour de l'entrée.
  Une ligne ouverte ne se modifie pas ; pour changer un stop, on clôt et on rouvre une ligne
  datée. Les setups pas pris ne sont pas ajoutés après coup (sinon on choisit les gagnants).
- Sortie uniquement sur **clôture hebdomadaire** (vendredi, vérifiée après 18 h) sous le stop
  ou au-dessus de l'objectif. Prix de sortie : celui de la ligne (`stop_exit`, `target_exit`) :
  un prix fixe, `open` (ouverture de la séance suivante) ou `close` (clôture de la semaine).
- Taille fixe : 2 % du capital fictif par setup. Frais : 0,2 % par côté. Pas de
  disjoncteurs : on mesure le fait de suivre les setups tels quels.
- Prix : Yahoo Finance (cours journaliers). Si un cours manque, la position ne bouge pas.

## Critère d'échec
En **mars 2027** (date prévue pour décider d'un éventuel satellite réel) :
- si l'écart moyen par trade clos avec l'ETF sur la même période est ≤ 0, **ou**
- si l'ensemble des setups fait moins bien que l'ETF,
on reste 100 % ETF. Avec moins de 20 trades clos, on ne conclut pas à un avantage : au mieux,
on sait si c'est nettement moins bon que l'ETF.

## Référence
`CW8.PA` (Amundi MSCI World, éligible PEA), du jour d'entrée au jour de sortie de chaque
trade. À remplacer par l'ETF réellement détenu si c'est un autre (`BENCHMARK` dans
`bot/strategies/setups.py`).

## Résultats
Au 2026-11-03 : 2 setups ouverts (Thales le 30/09 à 226,40 ; EssilorLuxottica le 16/10 à
153,20). La suite dans les revues hebdomadaires.
