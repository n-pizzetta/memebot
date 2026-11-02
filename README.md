# memebot — labo de stratégies (paper trading uniquement)

Un labo où des stratégies tournent côte à côte en **paper trading**, chacune avec son
capital fictif, son journal et ses versions figées. Les agents IA proposent et critiquent,
le code applique des règles fixes, les humains décident. Les règles sont dans
**[LAB.md](LAB.md)**, les hypothèses dans [`lab/hypotheses/`](lab/hypotheses/), l'historique
de tous les essais dans [`lab/REGISTRE.md`](lab/REGISTRE.md).

**Aucune clé, aucun wallet, aucun ordre réel.** Le code ne sait pas signer de transaction,
et un test le vérifie.

## Stratégies

| Stratégie | Version active | Fiche |
|---|---|---|
| `breakout` : cassure de plus haut avec volume, memecoins Solana de 24 h à 7 jours | v2 | [002](lab/hypotheses/002-breakout-v2.md) |

## Ce que fait un cycle (toutes les 15 min)

1. **Référence** : enregistre le prix du SOL, pour comparer chaque stratégie au fait de
   simplement garder du SOL.
2. **Positions ouvertes** : chaque position est suivie et clôturée avec les règles de la
   version qui l'a ouverte (stop, objectif, durée max, coûts). Un token dont le prix
   disparaît 3 runs de suite est compté à -100 %.
3. **Stratégies actives** : chacune fait son pas. Pour `breakout` :
   - collecte des pools tendance et des plus gros volumes sur GeckoTerminal ;
   - filtre rapide : âge 24 h – 7 j, liquidité ≥ 50 k$, volume 24 h ≥ 100 k$ ;
   - gates on-chain (rejet au moindre doute) : mint et freeze authority révoquées, pas
     d'extension Token-2022 dangereuse, top 10 holders ≤ 30 %, aucun risque « danger » sur
     RugCheck ;
   - signal : la dernière bougie horaire close dépasse le plus haut des 24 h précédentes,
     avec un volume ≥ 1,5 × la médiane.
4. **Module de risque commun** (`bot/paper.py`) : une bougie ouvre au plus un trade,
   position plafonnée pour qu'un rug coûte au plus 2 % du capital, 5 positions max, 40 %
   d'exposition max, disjoncteurs perte journalière (-3 %), série de pertes (4), flux de
   données en panne. Une stratégie qui plante n'arrête pas les autres.

Les réglages communs sont dans `bot/config.py`, ceux de chaque stratégie dans
`bot/strategies/<nom>.py`, une entrée par version. Chaque gate, disjoncteur et garde-fou
a un test dans `tests/` ; si un test échoue, le bot ne tourne pas.

## Lire les résultats

```bash
python -m bot.report            # sections "récentes" sur 7 jours
python -m bot.report --days 30
```

Le rapport donne, pour chaque stratégie et version, l'**espérance par trade après coûts**
en dollars et en % de la position, et la comparaison avec le fait de garder du SOL. Ne
concluez rien avant 100 trades clos. Si l'espérance est négative à 100 trades, la stratégie
n'a pas d'avantage : on change le signal (nouvelle version), pas les disjoncteurs.

Chaque lundi, une tâche planifiée écrit une revue dans `lab/revues/`, propose au plus une
modification sous forme de PR et envoie un résumé par e-mail. Rien n'est fusionné sans
relecture.

## Installation sur GitHub Actions (gratuit)

1. Dépôt public = minutes illimitées ; privé = mets le cron à 1x/heure dans
   `.github/workflows/collector.yml` pour rester dans le quota gratuit.
2. Onglet **Actions** → active les workflows → « paper-bot » → **Run workflow**.
3. Optionnel mais conseillé : crée une clé RPC gratuite chez Helius et ajoute-la dans
   Settings → Secrets → Actions sous le nom `SOLANA_RPC`. Le RPC public de Solana est
   souvent limité et provoque des rejets `check_error`. Le plan gratuit de Helius
   (1 M de crédits/mois) suffit : le bot consomme au pire ~220 k appels par mois.

Le résultat de chaque run s'affiche dans l'onglet Actions (résumé du run).

## Alternative : un petit VPS

```bash
git clone <ton dépôt> memebot && cd memebot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
crontab -e   # puis ajoute :
*/15 * * * * cd ~/memebot && .venv/bin/python -m bot.run >> run.log 2>&1
```

## Limites connues

- Les prix sont vérifiés toutes les 15 min : un stop peut être dépassé entre deux runs
  (c'est voulu, c'est plus proche de la réalité qu'un stop parfait). C'est pour ça que la
  taille est plafonnée sur le pire cas, pas sur le stop.
- L'exclusion des « programmes » dans le calcul du top 10 exclut aussi les tokens
  verrouillés ou en vesting de l'équipe.
- Les API gratuites (GeckoTerminal, RugCheck, RPC public) peuvent changer ou limiter ;
  le bot rejette alors les tokens au lieu de les accepter, et le rapport le montre.
- Le journal d'avant le labo (25/10 → 03/11) est rattaché à `breakout` v1, sans prix du SOL.
