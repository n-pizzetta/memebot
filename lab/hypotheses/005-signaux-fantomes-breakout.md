# 005 — Signaux fantômes : mesurer le signal breakout v2 sans le filtre des disjoncteurs

- **Statut** : proposée — pas encore codée
- **Stratégie / version** : mesure dans le rapport (ou collecte seule), aucune version de trading
- **Auteur** : agent (revue du 2026-11-09)
- **Date** : 2026-11-09

## Hypothèse
Les trades réels de breakout v2 ne sont pas un échantillon neutre de ses signaux : le disjoncteur
de série de pertes (4 pertes → 24 h de pause) choisit lesquels passent. Suivre aussi, en fictif
pur, chaque signal distinct (token + bougie) donne une mesure plus rapide et moins biaisée de
l'avantage du signal lui-même.

## Pourquoi c'est utile (chiffres du journal au 2026-11-09)
- 21 signaux distincts depuis le 03/11 ; 7 pris, **14 bloqués par `breaker_loss_streak`**.
- Depuis la 4e perte (04/11), v2 prend au plus ≈ 1 trade par jour : 100 trades clos demanderaient
  plusieurs mois.
- Rejeu manuel des 14 signaux bloqués sur les prix de `seen` : 7 objectifs, 7 stops (dont
  5 objectifs sur le seul token COGE). Les 7 trades réels : 7 stops. Trop peu pour conclure, assez
  pour voir que les deux populations peuvent diverger.

Ce n'est **pas** un moyen de contourner le disjoncteur ni de raccourcir le verdict : la fiche 002
reste jugée sur 100 trades réels. La mesure fantôme sert à interpréter ce verdict.

## Règles
- Pour chaque signal distinct de breakout v2 (première occurrence de `mint` + `signal_ts` dans
  `signals`), entrée fictive au prix du signal + 1,5 % de slippage.
- Suivi avec les prix déjà collectés à chaque run (`seen`, même stratégie-version), sans nouvel
  appel d'API : stop -15 %, objectif +30 %, sortie à 48 h, 1,5 % de slippage et 0,3 % de frais par
  côté (règles de v2).
- Token absent de `seen` pendant 3 runs de suite : compté à -100 % (comme
  `MISSES_BEFORE_ASSUMED_RUG`), car les tokens qui s'effondrent sortent de l'univers.
- Résultats donnés à part dans le rapport : pris / bloqués, espérance en % de la position,
  et nombre de **tokens** distincts (les bougies successives d'un même token sont corrélées).
- Aucun écrit dans `positions`, aucun effet sur le capital fictif ni sur les disjoncteurs.

## Critère d'échec (écrit avant toute mesure codée)
Sur les signaux **pris**, comparer le résultat fantôme au résultat réel. Si, après 20 trades réels
clos, l'écart moyen dépasse 10 points de % de la position, la mesure fantôme est jugée non fiable
(prix de `seen` trop différents de ceux des positions) et on l'abandonne.

## Référence
Les trades réels de breakout v2 sur les mêmes signaux, et garder du SOL.

## Résultats
—
