"""analyst-authored report narrative for the DECK initiating-coverage report.

This is the judgment layer — the words the owner must be able to defend aloud.
Every claim here is consistent with the engine's numbers and the
sourced assumptions in docs/ASSUMPTIONS.md; nothing overstates the model. Prose
is injected into the report template via ``build_html(..., narrative=...)`` —
the template owns structure, this owns the argument.

Keys map to the template's narrative sections (see build_html docstring).
Catalysts and risks are ``|``-separated bullet lists.
"""

from __future__ import annotations

# The full analyst narrative for DECK, as-of 2026-08-06 (price $99.68).
DECK_NARRATIVE: dict[str, str] = {
    "thesis": (
        "We initiate coverage of Deckers Outdoor (DECK) with a Buy rating and a "
        "12-month price target of $128, ~28% above the current $99.68. The market "
        "has re-rated DECK down to ~13x earnings and ~9x EV/EBITDA — near its "
        "52-week low — on a single fear: that revenue growth, having decelerated "
        "from +24% to +10%, is rolling over. We think that fear is overpriced. "
        "DECK is a net-cash (~$1.9B, zero debt), asset-light franchise whose "
        "operating margin has expanded ~500bp in four years to ~23% on HOKA's mix "
        "shift and a growing direct-to-consumer channel, and whose two brands — "
        "HOKA (still-growing performance running) and UGG (a mature, cash-"
        "generative franchise) — give it two independent ways to compound. Our DCF "
        "values the equity at ~$118–136/share (midpoint ~$127) even on deliberately "
        "conservative assumptions: growth decelerating further to 5%, a normalized "
        "steady-state terminal value, and an exit multiple of 11x — well below "
        "where premium footwear compounders trade at peak. The risk/reward is "
        "asymmetric: you are paying a trough multiple for a debt-free, high-return "
        "business that still grows."
    ),
    "catalysts": (
        "HOKA international expansion and new-franchise launches sustaining "
        "high-single-digit-plus growth as the U.S. run-rate matures"
        "|Continued gross-margin resilience near the ~58% record on DTC mix and "
        "disciplined promotion — refuting the 'margins have peaked' bear case"
        "|Aggressive buybacks against the ~$1.9B net-cash balance shrinking the "
        "share count (already ~146M to ~136M), compounding per-share value"
        "|A multiple re-rating back toward the peer/historical range as the market "
        "gains confidence that decelerating growth is not the same as no growth"
    ),
    "method_weighting": (
        "We weight the DCF most heavily (it best captures DECK's cash generation "
        "and net-cash balance sheet), cross-checked against trading comps and "
        "precedent transactions; the $128 target sits at the DCF midpoint (~$127) "
        "and squarely on the comps EV/EBITDA read (~$129) — a coherent triangulation."
    ),
    "company_overview": (
        "Deckers Outdoor designs and markets footwear and apparel under two "
        "flagship brands and several smaller ones. HOKA — performance running and "
        "trail footwear — is the growth engine, having scaled from a niche brand to "
        "the majority of incremental revenue on the strength of maximalist-cushion "
        "product and expanding retail distribution. UGG — sheepskin boots and "
        "casual footwear — is the mature, seasonally-weighted, highly cash-"
        "generative franchise that funds the portfolio. DECK is asset-light: "
        "manufacturing is outsourced, so capital intensity is low (~1.5% of "
        "revenue) and cash conversion is high. The company's fiscal year ends in "
        "March; it carries no debt and ~$1.9B of cash, and returns capital through "
        "share repurchases rather than a dividend."
    ),
    "industry": (
        "The athletic and casual footwear market is large, brand-driven, and "
        "competitive, spanning global scale players (Nike) and focused challengers "
        "(Crocs, On, Birkenstock). DECK competes on brand equity and product "
        "differentiation rather than price, and its DTC shift lets it capture "
        "full retail margin and own the customer relationship. We select the peer "
        "set for comparability of driver story — brand-led footwear/apparel with "
        "meaningful DTC — spanning pure footwear names (Nike, Crocs, Steve Madden), "
        "diversified apparel (VF Corp, Columbia, Wolverine), and footwear retail "
        "(Boot Barn, Caleres). No single peer is a perfect match, which is why we "
        "anchor valuation on the DCF and use comps as a triangulation check."
    ),
    "financial_analysis": (
        "DECK's five-year record is one of durable growth with structural margin "
        "gains: revenue compounded from ~$3.2B (FY22) to ~$5.5B (FY26) while gross "
        "margin expanded ~700bp to ~58% and operating margin rose to ~23%, driven "
        "by HOKA's favorable mix and the DTC shift. Free cash flow has been strong "
        "and rising (operating cash flow ~$1.2B in FY26), funding an accumulating "
        "net-cash position and steady buybacks. Our forecast extends this pattern "
        "conservatively: revenue growth glides from ~9% to ~5% over five years "
        "(continuing the observed deceleration rather than assuming a cliff or a "
        "reacceleration), gross margin eases modestly off the record as promotional "
        "intensity normalizes, and capital intensity stays low. The result is "
        "continued high-return, cash-generative growth — the engine of the DCF."
    ),
    "target_derivation": (
        "Our $128 12-month target is derived primarily from the DCF, which implies "
        "~$118 on the Gordon-growth terminal (g=3%, built on a normalized "
        "steady-state terminal free cash flow) and ~$136 on an 11x exit EV/EBITDA "
        "(discounted as a year-end sale), for a midpoint near $127. Trading comps "
        "sanity-check the call at ~$129 on peer-median EV/EBITDA (peer market data "
        "is illustrative, so we treat comps as a cross-check, not independent "
        "confirmation). The $128 target therefore sits at the DCF midpoint and on "
        "the comps read. Framed as a reverse-DCF, the market is pricing something bleaker "
        "than mere caution: even a zero-terminal-growth version of our DCF is worth "
        "~$108 — above today's ~$100 — so the price implies the perpetuity actually "
        "*shrinks* in real terms, not just decelerates. That is the crux of the "
        "decelerating-not-declining debate, and we think it is too harsh for a "
        "debt-free brand still growing high-single-digits. Note the net-cash "
        "balance sheet makes enterprise value smaller "
        "than equity value — the ~$1.9B of cash is added back in the bridge, a "
        "detail that flatters per-share value relative to leveraged peers."
    ),
    "risks": (
        "Growth deceleration proves structural, not cyclical: if HOKA's momentum "
        "stalls or the brand cycles, the whole thesis weakens — this is the "
        "central risk and the reason the stock is where it is"
        "|Fashion/seasonality risk at UGG: a warm winter or a shift in taste can "
        "swing a large, high-margin portion of profit"
        "|Margin give-back: the ~58% gross margin is at a record; renewed "
        "promotional intensity, freight inflation, or tariff exposure on outsourced "
        "manufacturing could compress it faster than we model"
        "|Multiple risk: our target assumes a partial re-rating; if the market "
        "keeps DECK at a trough multiple despite steady execution, returns come "
        "only from earnings growth and buybacks, not re-rating"
        "|Concentration and competition: two brands drive nearly all value, in a "
        "category where well-funded competitors (Nike, On, Birkenstock) contest the "
        "same consumer"
    ),
}
