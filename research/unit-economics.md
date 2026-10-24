# Harvestly unit economics sketch (2026-10-12)

**ASSUMPTION** marks anything I made up. Prices are KES, VAT-inclusive where stated. FX assumed US$1 = KES 129 (ASSUMPTION).

## Price inputs found
| Input | Value | Source / status |
|---|---|---|
| Africa's Talking bulk SMS, Safaricom | KES 0.8 per SMS at Basic tier (top-ups under KES 20,000), falling to KES 0.4 at Max tier (top-ups from KES 400,000); other Kenyan networks 0.8 to 0.6; Airtel international USD 0.22 | https://africastalking.com/sms/bulksms and https://africastalking.com/pricing: primary, but read only through search-result summaries (direct fetch 403). Third-party blogs quote KES 0.4-0.8 (secondary). Confirm with AT sales. |
| Shared shortcode (keyword) | UNVERIFIED: "setup KES 5,000 + 16% VAT = 5,800; monthly KES 2,000 + VAT = 2,320" came from a search summary; review R1 found no source. Do not publish or rely on it; excluded from the totals below | unverified |
| Dedicated shortcode (older article, possibly outdated) | KES 15,000 + VAT = 17,400 per network, plus deposit | https://help.africastalking.com/en/articles/1142375-how-much-is-a-dedicated-short-code (stale, ~7 years old) |
| Sender ID | free to raise now per AT bulk page; older article KES 8,700 | AT page (summary) / older help article |
| **Dedicated USSD code, Kenya** (page dated 27 May 2025, VAT incl.) | Safaricom: test bed 17,400 (1 month), setup 145,000 (3-4 weeks), **70,000 a month**. Airtel: setup 116,000, 46,400 a month. Telkom: setup 58,000, 116,000 a month. One-off deposit 28,500 | **Verified at primary**: https://help.africastalking.com/en/articles/1163556-how-much-is-a-dedicated-ussd-code |
| Shared USSD code and per-session fee | **Not found.** Blogs claim shared codes about KES 3,000 a month and KES 0.25-1.50 per session: unreliable | secondary, conflicting |
| Safaricom approval | Setup lead time 3-4 weeks after payment per the AT page above. No public Safaricom document found on approval criteria | primary for lead time only |
| Oracle ADB, APEX | Always Free: KES 0 | primary |
| Open-Meteo | free tier is non-commercial; commercial plan price not checked | per the note [29] |

## Messages per farmer per season (4 months, ASSUMPTION)
The engine caps at one unprompted message a day and sends only on change, plus capped reminders. Each message is at most 2 SMS.
| Scenario | Outbound SMS per farmer | Basis |
|---|---|---|
| Low | 15 | few changes, a hermetic-bag farmer, dry grain |
| Base | 40 | about 25 messages averaging 1.6 SMS: registration, test prompts (max 3), a few rain/countdown alerts, reminders |
| High | 100 | wet El Niño season, many rain alerts |
| Theoretical cap | 240 | 1 a day x 2 SMS x 120 days: not reachable given the spacing rules |

## Per-farmer-per-season cost, SMS only
| Rate | Low | Base | High |
|---|---|---|---|
| KES 0.8 (Basic tier; search snippet only) | 12 | 32 | 80 |
| KES 0.4 (Max tier) | 6 | 16 | 40 |
So **about KES 30 (US$0.25) per farmer per season at base case**, KES 6-80 across the range.

**Open issue (so we never say "farmers never pay"):** a farmer's reply (SALT YES, METER 13.2, 1) is an inbound SMS, normally billed to the farmer at the network's ordinary SMS rate (about KES 1 on Safaricom, ASSUMPTION, not checked) unless the shortcode is toll-free or reverse-billed. 5-10 replies per season is KES 5-10 per farmer. Either confirm with AT that the shared keyword is free to the sender, or say only that the pilot design does not charge farmers for alerts. Who pays for inbound SMS to a shared shortcode depends on the shortcode type and is not settled.

## Fixed channel cost (one 4-month season, same basis for every scenario)
| Option | Cost | Notes |
|---|---|---|
| SMS only | KES 0 fixed that we can source | A shared shortcode for replies is needed in practice, but its price is UNVERIFIED (no source found), so it is excluded |
| Add dedicated Safaricom USSD | 145,000 + 4 x 70,000 = **KES 425,000** (US$3,300) | verified at AT page of 27 May 2025; plus a one-off KES 28,500 deposit and AT per-session fees (not found), both excluded. 12 months would be KES 985,000 |
| Add dedicated Airtel USSD | 116,000 + 4 x 46,400 = KES 301,600 | Airtel has far fewer maize farmers (market share ASSUMPTION) |
| Shared USSD | unknown: ask AT for a quote | the realistic path for a pilot |

## Scenarios (base-case SMS use, KES 0.8; one 4-month season each)
| | Pilot, 200 farmers | County, 10,000 farmers |
|---|---|---|
| SMS | 200 x 32 = 6,400 | 10,000 x 32 = 320,000 (160,000 at Max tier) |
| Shared shortcode | excluded (price unverified) | excluded (price unverified) |
| Dedicated Safaricom USSD (4 months) | not used | 425,000 |
| **Total, SMS only** | **KES 6,400 (US$50): KES 32 per farmer** | **KES 320,000: KES 32 per farmer** |
| **Total, with dedicated USSD** | n/a | **KES 745,000: KES 75 per farmer** (74.5 rounded half up) |
Earlier versions of this file mixed a 12-month shortcode cost into the county row and a 4-month cost into the pilot row, and counted the unverified shortcode price; both are fixed here (review R1-029). Staff, support, M&E, Kiswahili review and meter spot checks are excluded and will dominate the pilot cost. Meter spot checks need a meter (not priced; ASSUMPTION about KES 8,000-15,000 each).

**Takeaway for the pitch:** messaging costs about KES 32 per farmer-season on our assumptions (40 SMS at KES 0.8, both unconfirmed). A dedicated USSD code only makes sense above roughly 10,000 farmers or when a payer wants it; below that, SMS.

## Who could pay, and how much it must cover
| Payer | Why they would | Price test (ASSUMPTION) | Honest caveat |
|---|---|---|---|
| County government (Trans Nzoia) | devolved extension; KMD advisory already calls for drying and hermetic storage | KES 50-100 per farmer-season: 10,000 farmers = KES 0.5-1.0M | public budgets are slow; a procurement process, not a hackathon prize |
| Co-operatives and aggregators | fewer rejected or mouldy deliveries; they need moisture data | KES 20-50 per farmer-season, or per referred tonne | co-op margins are thin; most pay only after seeing results |
| NCPB / warehouse-receipt operators | dry grain at intake lowers drying cost (NCPB reportedly set drying at about KES 70 per 90 kg bag, down from over 300; undated report, unverified) | per referred tonne passing 13.5%: KES 20-50 (ASSUMPTION). A farmer with 10 bags (0.9 t) is KES 18-45, about the SMS cost | NCPB is slow to contract; there is no evidence yet that referrals convert |
| Hermetic bag makers and stockists | a bag costs KES 250-300 per the one source found [35], which appears to describe ordinary bags (hermetic price unconfirmed); a referral commission, say 5% = KES 12-15 per bag | listing fee or commission | conflict of interest; the note already says payment never changes advice |
| Insurers / lenders | fewer storage losses on financed grain | none quantified | no evidence found; speculative. Note: insurance and financial services are non-exempt ODPC categories |
| MoA-INFO / KAOP licensing | reuse of their channel | licence fee, unknown | no conversation held; do not claim interest |
| Donors / grants (AICCRA, CGIAR) | evidence generation | pilot grant | not a business model |

Break-even: farmer-season cost about KES 32 ex-USSD. A per-tonne fee of KES 40 on 0.9 t covers it only if the farmer actually delivers to a paying warehouse, which may be a minority. One possible early model, not decided: a county or donor pays for a pilot, per-tonne fees come later. Every payer price in this file is an ASSUMPTION.
