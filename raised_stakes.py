"""Pairs the live follower trades at a raised stake (2026-11-05, Olu).

The follower sizes each order from its own config, risk.stake_usd_by_pair, on the VPS; the public
pages are built here and cannot read that file. This is its copy, by hand: a pair listed here gets a small "Raised
stake" badge on its sport page's rule row. No amount is printed anywhere (public copy: sandbox_audit.COPY_RE), and
nothing here changes what the follower does. Update it when the follower's config changes.

Read from the follower's config 2026-11-05: mls_fade_home|soccer_p05, commod_fav_band|commodities_fav and
crypto_fav_band_below|crypto_fav carry their own stake; every other pair trades at the default.
"""

RAISED = {
    "mls_fade_home|soccer_p05": "2026-11-05",
    "commod_fav_band|commodities_fav": "2026-11-05",
    "crypto_fav_band_below|crypto_fav": "2026-11-05",
}


def raised(pair):
    """True when the follower trades this Production pair ("source|sport") at a raised stake."""
    return pair in RAISED
