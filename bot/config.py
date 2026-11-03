"""Hard limits. They live in code on purpose: changing one means a commit, not a slider.

Ce fichier contient ce qui est commun à tout le labo (univers Solana, gates, endpoints,
garde-fous globaux). Les réglages propres à une stratégie (signal, sorties, taille) sont
dans bot/strategies/<nom>.py, une entrée par version.
"""
import os
from dataclasses import dataclass

# --- Garde-fous du labo (vérifiés par tests/test_lab.py) -----------------------
PAPER_START_BOOK = 1_000.0  # capital fictif de départ de chaque stratégie-version (USD)
MAX_LOSS_ON_TOTAL_FAILURE = 0.02  # une position qui tombe à zéro (rug) coûte au plus 2 % du capital
MISSES_BEFORE_ASSUMED_RUG = 3  # prix introuvable 3 runs de suite => on compte -100 %


@dataclass(frozen=True)
class Risk:
    """Taille, sorties, coûts et disjoncteurs d'une version de stratégie.
    Les valeurs par défaut sont celles de breakout v1 (25/10/2026)."""
    risk_per_trade: float = 0.01        # 1 % du capital ACTUEL perdu si le stop est respecté
    max_position_fraction: float = 0.10
    max_exposure_fraction: float = 0.40
    max_open_positions: int = 5
    stop_pct: float = -15.0
    target_pct: float = 30.0
    max_hold_h: float = 48
    slippage_pct: float = 1.5           # par côté, volontairement pessimiste
    fee_pct: float = 0.3                # frais de swap par côté
    daily_loss_cap: float = 0.03        # -3 % du capital sur la journée UTC => plus d'entrée
    max_loss_streak: int = 4            # 4 pertes d'affilée => pause
    loss_streak_pause_h: float = 24


# --- Univers memecoins Solana : seulement les "survivants" ----------------------
MIN_AGE_H = 24              # on ignore les tokens de moins de 24 h (zone des rugs)
MAX_AGE_H = 24 * 7          # et ceux de plus de 7 jours
MIN_LIQ_USD = 50_000        # liquidité mini du pool pour pouvoir sortir
MIN_VOL_24H_USD = 100_000   # volume mini sur 24 h
TRENDING_PAGES = 3          # pages GeckoTerminal "trending pools" scannées par run
TOP_VOLUME_PAGES = 5        # + pages "plus gros volume 24 h" pour élargir l'univers
MAX_DEEP_CHECKS = 25        # nb max de tokens vérifiés on-chain par run (limites d'API)

# --- Gates (éliminatoires) -----------------------------------------------
MAX_TOP10_PCT = 30.0        # top 10 holders (hors pools / programmes) > 30 % => rejet
BANNED_TOKEN2022_EXTENSIONS = {
    "transferHook", "permanentDelegate", "transferFeeConfig",
    "nonTransferable", "defaultAccountState", "pausableConfig",
}
USE_RUGCHECK = True         # rejet si RugCheck signale un risque de niveau "danger"

# --- Endpoints -----------------------------------------------------------------
GECKO = "https://api.geckoterminal.com/api/v2"
GECKO_MIN_INTERVAL_S = 2.2  # API gratuite ~30 req/min
RPC = os.environ.get("SOLANA_RPC") or "https://api.mainnet-beta.solana.com"
RUGCHECK = "https://api.rugcheck.xyz/v1"
YAHOO = "https://query1.finance.yahoo.com"  # cours journaliers des actions (stratégie setups)
DB_PATH = os.environ.get("DB_PATH", "data/journal.db")

WSOL = "So11111111111111111111111111111111111111112"
SKIP_MINTS = {
    WSOL,
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}
