# 005 — Signaux fantômes : mesurer le signal breakout v2 sans le filtre des disjoncteurs

- **Statut** : codée dans le rapport (`bot/ghost.py`, revue du 2026-11-16), mesure seule
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

## Mise en œuvre (2026-11-16)
- `bot/ghost.py`, section « Signaux fantômes » de `python -m bot.report`. Lecture seule (testé).
- Un signal est « pris » si l'une de ses occurrences a donné `paper_entry` ; l'entrée fantôme reste
  au prix de la **première** occurrence (cas Leonida du 10/11 : bloqué à 21:00, pris à 21:45).
- Seuls les runs `ok` comptent comme ratés pour la règle des 3 absences.
- Règle des -100 % conservée telle qu'écrite. Le rapport affiche **en plus** l'espérance si les
  tokens disparus sortaient à leur dernier prix vu, car le journal montre qu'un token peut quitter
  l'univers sans rug : BIG / TTWO (signaux du 13/11) a disparu le 14/11 à 05:30 alors que son
  dernier prix vu était au-dessus de l'entrée et sa liquidité à 104 k$ (sorti des listes, volume
  24 h ≈ 100 k$). Le critère d'échec ci-dessus n'est pas modifié.

## Résultats
Au 2026-11-16 (29 signaux distincts, 17 tokens) : pris 12 → espérance fantôme -33,8 % ; bloqués 17
→ -6,8 % (7 objectifs, 2 disparus comptés -100 %). Écart fantôme − réel sur les 12 pris : -1,7 point
en moyenne, 2,6 points en absolu (critère d'échec évalué à 20 trades réels clos).
