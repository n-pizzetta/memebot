"""Registre des stratégies du labo.

Une stratégie = un module avec :
  NAME      identifiant court, unique (sert dans le journal et le capital fictif)
  ACTIVE    numéro de la version qui prend de nouvelles positions (None = en pause)
  VERSIONS  {numéro: Version(...)} — on n'en modifie JAMAIS une qui a tradé
  prices(mints) -> {mint: prix_usd}       pour suivre et clôturer ses positions
  step(ctx) -> dict de stats              un cycle : univers, filtres, signaux, ctx.desk.consider(...)

Voir LAB.md avant d'en ajouter ou d'en modifier une.
"""
from dataclasses import dataclass

from ..config import Risk


@dataclass(frozen=True)
class Version:
    risk: Risk
    since: str          # date de mise en service (AAAA-MM-JJ)
    hypothesis: str     # fichier lab/hypotheses/... qui la justifie
    note: str           # ce qui change par rapport à la version précédente


from . import breakout, setups  # noqa: E402

REGISTRY = {m.NAME: m for m in (breakout, setups)}
