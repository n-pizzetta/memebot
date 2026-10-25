# memebot — phase 1 (paper trading uniquement)

Collecte les tokens Solana « survivants » (24 h – 7 jours), les passe dans des filtres
éliminatoires, détecte les cassures de plus haut avec volume et **simule** des trades.
Tout est enregistré dans `data/journal.db` (SQLite).

**Aucune clé, aucun wallet, aucun ordre réel.** Le code ne sait pas signer de transaction.

## Ce que fait un cycle

1. **Collecte** : pools tendance Solana sur GeckoTerminal (3 pages).
2. **Filtre rapide** : âge 24 h – 7 j, liquidité ≥ 50 k$, volume 24 h ≥ 100 k$.
3. **Gates on-chain** (rejet au moindre doute) : mint authority et freeze authority
   révoquées, pas d'extension Token-2022 dangereuse, top 10 holders ≤ 30 %
   (pools et programmes exclus), aucun risque « danger » sur RugCheck.
4. **Signal** : la dernière bougie horaire close dépasse le plus haut des 24 h
   précédentes, avec un volume ≥ 1,5× la médiane.
5. **Risque** : 1 % du capital actuel risqué par trade, 5 positions max, 40 %
   d'exposition max, disjoncteurs perte journalière (-3 %), série de pertes (4),
   flux de données en panne.
6. **Paper trading** : entrée et sortie avec 1,5 % de slippage et 0,3 % de frais par
   côté, stop -15 %, objectif +30 %, sortie forcée à 48 h. Un token dont le prix
   disparaît 3 runs de suite est compté à -100 %.

Tous les seuils sont dans `bot/config.py`. Chaque gate et chaque disjoncteur a un test
dans `tests/` ; si un test échoue, le bot ne tourne pas.

## Installation sur GitHub Actions (gratuit)

1. Crée un dépôt sur github.com (public = minutes illimitées ; privé = mets le cron à
   1x/heure dans `.github/workflows/collector.yml` pour rester dans le quota gratuit).
2. Envoie tous les fichiers de ce dossier dans le dépôt (bouton « Add file » →
   « Upload files », en gardant le dossier `.github`).
3. Onglet **Actions** → active les workflows → « paper-bot » → **Run workflow**.
4. Optionnel mais conseillé : crée une clé RPC gratuite chez Helius et ajoute-la dans
   Settings → Secrets → Actions sous le nom `SOLANA_RPC`. Le RPC public de Solana est
   souvent limité et provoque des rejets `check_error`.

Le résultat de chaque run s'affiche dans l'onglet Actions (résumé du run).

## Alternative : un petit VPS

```bash
git clone <ton dépôt> memebot && cd memebot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
crontab -e   # puis ajoute :
*/15 * * * * cd ~/memebot && .venv/bin/python -m bot.run >> run.log 2>&1
```

Rapport à tout moment : `python -m bot.report`

## Lire les résultats

Le rapport donne l'**espérance par trade** après coûts. C'est le seul chiffre qui
compte. Ne conclus rien avant 100 trades clos, et compare au simple fait de garder
du SOL sur la même période. Si l'espérance est négative à 100 trades, la stratégie
n'a pas d'avantage : on change le signal, pas les disjoncteurs.

## Limites connues

- Les prix sont vérifiés toutes les 15 min : un stop peut être dépassé entre deux
  runs (c'est voulu, c'est plus proche de la réalité qu'un stop parfait).
- L'exclusion des « programmes » dans le calcul du top 10 exclut aussi les tokens
  verrouillés ou en vesting de l'équipe.
- Les API gratuites (GeckoTerminal, RugCheck, RPC public) peuvent changer ou limiter ;
  le bot rejette alors les tokens au lieu de les accepter, et le rapport le montre.
