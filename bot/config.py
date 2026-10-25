"""Hard limits. They live in code on purpose: changing one means a commit, not a slider."""
import os

# --- Univers : seulement les "survivants" ---------------------------------
MIN_AGE_H = 24              # on ignore les tokens de moins de 24 h (zone des rugs)
MAX_AGE_H = 24 * 7          # et ceux de plus de 7 jours
MIN_LIQ_USD = 50_000        # liquidité mini du pool pour pouvoir sortir
MIN_VOL_24H_USD = 100_000   # volume mini sur 24 h
TRENDING_PAGES = 3          # pages GeckoTerminal "trending pools" scannées par run
MAX_DEEP_CHECKS = 25        # nb max de tokens vérifiés on-chain par run (limites d'API)

# --- Gates (éliminatoires) -----------------------------------------------
MAX_TOP10_PCT = 30.0        # top 10 holders (hors pools / programmes) > 30 % => rejet
BANNED_TOKEN2022_EXTENSIONS = {
    "transferHook", "permanentDelegate", "transferFeeConfig",
    "nonTransferable", "defaultAccountState", "pausableConfig",
}
USE_RUGCHECK = True         # rejet si RugCheck signale un risque de niveau "danger"

# --- Signal : cassure de plus haut avec volume -----------------------------
BREAKOUT_LOOKBACK_H = 24    # la bougie close doit dépasser le plus haut des 24 h précédentes
VOLUME_MULT = 1.5           # ... avec un volume >= 1,5 x la médiane des 24 h précédentes

# --- Paper trading -----------------------------------------------------------
PAPER_START_BOOK = 1_000.0  # capital fictif de départ (USD)
RISK_PER_TRADE = 0.01       # 1 % du capital ACTUEL risqué par trade
MAX_POSITION_FRACTION = 0.10
MAX_EXPOSURE_FRACTION = 0.40
MAX_OPEN_POSITIONS = 5
STOP_PCT = -15.0
TARGET_PCT = 30.0
MAX_HOLD_H = 48
SLIPPAGE_PCT = 1.5          # par côté, volontairement pessimiste
FEE_PCT = 0.3               # frais de swap par côté
MISSES_BEFORE_ASSUMED_RUG = 3  # prix introuvable 3 runs de suite => on compte -100 %

# --- Disjoncteurs ------------------------------------------------------------
DAILY_LOSS_CAP = 0.03       # -3 % du capital sur la journée UTC => plus d'entrée
MAX_LOSS_STREAK = 4         # 4 pertes d'affilée => pause
LOSS_STREAK_PAUSE_H = 24

# --- Endpoints -----------------------------------------------------------------
GECKO = "https://api.geckoterminal.com/api/v2"
GECKO_MIN_INTERVAL_S = 2.2  # API gratuite ~30 req/min
RPC = os.environ.get("SOLANA_RPC") or "https://api.mainnet-beta.solana.com"
RUGCHECK = "https://api.rugcheck.xyz/v1"
DB_PATH = os.environ.get("DB_PATH", "data/journal.db")

SKIP_MINTS = {
    "So11111111111111111111111111111111111111112",   # wSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}
