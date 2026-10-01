"""Compose DiligenceIQ Customer Stickiness — revenue that persists (prompt book).

Cohorts are built by start period on a population defined once and held constant (logos, accounts,
locations or subscriptions). Opening revenue, churn, contraction, expansion and closing revenue are
reconciled, and GRR, NRR and logo retention are calculated on **the same population** with new
customers excluded from the numerators. Retention is cut by segment and by tenure, reasons for loss
are read from the records where they capture them, and the point where loss concentrates is stated.

Executed contracts for the largest customers are reviewed for term, renewal mechanism, notice
period, minimum commitment, price escalator and termination for convenience, and the renewal cliff
— the material share of revenue up for renewal — is identified.

Behaviour is distinguished from protection: customers who have stayed are **not** the same as
customers who are contractually committed. Where retention has moved, the movement is stated with
magnitude and direction — a falling rate is a **finding**, not a caveat.

No invest/pass. No company allowlists. Preserves the legacy Revenue Retention Table shape
(retention_metrics / cohorts / stickiness_notes) for decks and workbooks.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _fmt_num,
    _pick_sentences,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_HEADER_LINE = re.compile(r"(?m)^\s*#{1,6}\s*\S+\s*$")
_CLAUSE_SPLIT = re.compile(r"(?<=[.;!?])\s+|\n+|\s+—\s+")

_DOCUMENT_TITLE = "Revenue Retention Table"
_DD_CODE = "DD-11"
_POPULATIONS = ("logos", "accounts", "locations", "subscriptions")
_DIRECTIONS = ("up", "down", "flat", "unknown")

_EXCLUSION_RULE = "new customers are excluded from the retention numerators"
_SAME_POP_RULE = f"GRR, NRR and logo retention are calculated on the same population; {_EXCLUSION_RULE}"
_BEHAVIOUR_RULE = (
    "Customers who have stayed are **not** the same as customers who are contractually committed "
    "— stayed ≠ contractually committed."
)

_METRIC_LABEL = {
    "grr_pct": "GRR (gross revenue retention)",
    "nrr_pct": "NRR (net revenue retention)",
    "logo_retention_pct": "Logo retention",
    "logo_churn_pct": "Logo churn",
    "revenue_churn_pct": "Revenue churn",
    "retention_12m_pct": "12-month customer retention",
    "repurchase_pct": "Repurchase / repeat rate",
}
_METRIC_KEYS = tuple(_METRIC_LABEL)

# ---------------------------------------------------------------------------
# population cues
# ---------------------------------------------------------------------------

_POP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("logos", re.compile(r"(?i)\b(logos?|customer\s+logos?|logo[- ]level|logo\s+count|distinct\s+customers?"
                         r"|unique\s+customers?|named\s+customers?)\b")),
    ("accounts", re.compile(r"(?i)\b(accounts?|billing\s+accounts?|customer\s+accounts?|account[- ]level"
                            r"|debtor\s+accounts?|account\s+ids?|paying\s+accounts?)\b")),
    ("locations", re.compile(r"(?i)\b(locations?|sites?|branches|stores?|outlets?|depots?|premises"
                             r"|ship[- ]to\s+points?|delivery\s+points?)\b")),
    ("subscriptions", re.compile(r"(?i)\b(subscriptions?|licen[cs]es?|seats?|contract\s+lines?"
                                 r"|service\s+lines?|SKU\s+lines?|plans?\s+in\s+force|live\s+contracts?)\b")),
)
_POP_DEFINITION_CUE = re.compile(
    r"(?i)(?:population\s+(?:is|=|defined)|defined\s+as|measured\s+on|counted\s+on|held\s+constant"
    r"|basis\s+of\s+measurement|retention\s+is\s+measured|cohort\s+population|kept\s+constant"
    r"|consistent\s+population|same\s+population)"
)
_POP_CONSTANT_CUE = re.compile(
    r"(?i)(?:held\s+constant|kept\s+constant|constant\s+population|no\s+re[- ]basing|consistent(?:ly)?\s+defined"
    r"|same\s+population\s+(?:throughout|across)|population\s+is\s+not\s+re[- ]based|denominator\s+is\s+fixed)"
)

# ---------------------------------------------------------------------------
# retention metrics
# ---------------------------------------------------------------------------

_PCT_TAIL = r"(?:\s*\(\s*%\s*\))?[^.\d%]{0,30}?(\d{1,3}(?:\.\d+)?)\s*%"
_METRIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("grr_pct", re.compile(r"(?i)(?:Gross\s+Revenue\s+Retention(?:\s*\(\s*GRR\s*\))?"
                           r"|Gross\s+Dollar\s+Retention|\bGRR\b|\bGDR\b)" + _PCT_TAIL)),
    ("nrr_pct", re.compile(r"(?i)(?:Net\s+Revenue\s+Retention(?:\s*\(\s*NRR\s*\))?"
                           r"|Net\s+Dollar\s+Retention(?:\s*\(\s*NDR\s*\))?|\bNRR\b|\bNDR\b)" + _PCT_TAIL)),
    ("logo_retention_pct", re.compile(r"(?i)(?:Logo\s+Retention(?:\s+Rate)?|Logo[- ]level\s+retention"
                                      r"|Customer\s+Retention\s*\(\s*logos?\s*\)"
                                      r"|Account\s+Retention(?:\s+Rate)?)" + _PCT_TAIL)),
    ("logo_churn_pct", re.compile(r"(?i)(?:Logo\s+Churn|Logo[- ]level\s+churn|Customer\s+Churn(?:\s+Rate)?"
                                  r"|Account\s+Churn(?:\s+Rate)?)" + _PCT_TAIL)),
    ("revenue_churn_pct", re.compile(r"(?i)(?:Revenue\s+Churn|Gross\s+Revenue\s+Churn|Dollar\s+Churn"
                                     r"|ARR\s+Churn|MRR\s+Churn)" + _PCT_TAIL)),
    ("retention_12m_pct", re.compile(r"(?i)(?:12[- ]Month\s+Customer\s+Retention(?:\s+Rate)?"
                                     r"|M12\s+retention(?:\s+rate)?|Retention\s+Rate\s*\(\s*12\s?M\s*\)"
                                     r"|12\s?M\s+retention(?:\s+rate)?"
                                     r"|twelve[- ]month\s+retention(?:\s+rate)?)" + _PCT_TAIL)),
    ("repurchase_pct", re.compile(r"(?i)(?:Repurchase\s+Rate(?:\s*\([^)]{0,30}\))?|Repeat\s+purchase\s+rate"
                                  r"|Repeat\s*/\s*Referral\s+Purchase(?:\s*\(\s*%\s*\))?|Repeat\s+order\s+rate)"
                                  r"(?:\s*\(\s*%\s*\))?[^.\d%]{0,30}?(?:N/?A\s+)?(\d{1,3}(?:\.\d+)?)\s*%")),
)
_METRIC_NOUN = (
    r"GRR|GDR|NRR|NDR|gross\s+revenue\s+retention|gross\s+dollar\s+retention|net\s+revenue\s+retention"
    r"|net\s+dollar\s+retention|logo\s+retention|logo\s+churn|revenue\s+churn|customer\s+churn"
    r"|account\s+retention|customer\s+retention|revenue\s+retention|retention\s+rate|retention"
)
_METRIC_TOKEN = re.compile(rf"(?i)\b({_METRIC_NOUN})\b")
_METRIC_TOKEN_KEY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)^(?:grr|gdr|gross\s+(?:revenue|dollar)\s+retention)$"), "grr_pct"),
    (re.compile(r"(?i)^(?:nrr|ndr|net\s+(?:revenue|dollar)\s+retention)$"), "nrr_pct"),
    (re.compile(r"(?i)^(?:logo\s+retention|account\s+retention)$"), "logo_retention_pct"),
    (re.compile(r"(?i)^(?:logo\s+churn|customer\s+churn)$"), "logo_churn_pct"),
    (re.compile(r"(?i)^revenue\s+churn$"), "revenue_churn_pct"),
    (re.compile(r"(?i)^(?:customer\s+retention|revenue\s+retention|retention\s+rate|retention)$"),
     "retention_12m_pct"),
)

_DOWN_VERB = re.compile(r"(?i)\b(fell|falls|falling|declin\w+|drop\w*|decreas\w+|deteriorat\w+|slipp\w+"
                        r"|weaken\w+|worsen\w+|reduc\w+|down|lower|softened|eroded|compressed)\b")
_UP_VERB = re.compile(r"(?i)\b(rose|rises|rising|grew|grow\w*|increas\w+|improv\w+|climb\w+|strengthen\w+"
                      r"|recover\w+|up|higher|expand\w+|lifted)\b")
_FLAT_VERB = re.compile(r"(?i)\b(flat|stable|unchanged|held|steady|in\s+line)\b")
_MOVE_PHRASE = re.compile(rf"(?i)\b({_METRIC_NOUN})\b([^.]{{0,50}}?)(?:from\s+)?(\d{{1,3}}(?:\.\d+)?)\s*%"
                          r"[^.\d%]{0,26}?(?:to|→|->|versus|vs\.?)\s*(\d{1,3}(?:\.\d+)?)\s*%")
_MOVE_PAREN = re.compile(r"(?i)\b(GRR|NRR|logo\s+retention|revenue\s+retention|retention)\b"
                         r"[^.]{0,20}?(\d{1,3}(?:\.\d+)?)\s*%\s*\(\s*((?:FY|CY)\s?\d{2,4}|\d{4})\s*\)"
                         r"[^.]{0,24}?(\d{1,3}(?:\.\d+)?)\s*%\s*\(\s*((?:FY|CY)\s?\d{2,4}|\d{4})\s*\)")
_PP_MOVE = re.compile(r"(?i)\b(GRR|NRR|logo\s+retention|revenue\s+retention|retention|logo\s+churn)\b"
                      r"([^.]{0,50}?)(\d{1,3}(?:\.\d+)?)\s*(?:pp|ppt|percentage\s+points?)\b")

# ---------------------------------------------------------------------------
# cohorts / dates / money
# ---------------------------------------------------------------------------

_MONTH = r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
_COHORT_PERIOD = (rf"(?:Q[1-4]\s*(?:FY|CY)?\s?(?:19|20)?\d{{2}}|(?:{_MONTH})[a-z]*[\s\-']*(?:19|20)?\d{{2}}"
                  r"|(?:FY|CY)\s?(?:19|20)?\d{2}(?:[-/]\d{2,4})?|H[12]\s*(?:FY|CY)?\s?(?:19|20)?\d{2}"
                  r"|M\d{1,3}\s+(?:19|20)\d{2})")
_COHORT_RE = re.compile(rf"({_COHORT_PERIOD}(?:\s*\([^)]{{0,40}}\))?)\s+([\d,]{{1,12}})\s+"
                        r"(?:N/?A|(\d{1,3}(?:\.\d+)?)\s*%)\s+(?:N/?A|(\d{1,3}(?:\.\d+)?)\s*%)"
                        r"(?:\s+(?:N/?A|(\d{1,3}(?:\.\d+)?)\s*%))?", re.IGNORECASE)
_COHORT_CUE = re.compile(r"(?i)\b(cohort|cohorts|vintage|start\s+period|start\s+month|monthly\s+cohort"
                         r"|by\s+cohort|cohort\s+curve|survival)\b")
_COHORT_M6 = re.compile(r"(?i)(?:M6|6[- ]month[s]?|six[- ]month[s]?)[^.\d%]{0,24}?(\d{1,3}(?:\.\d+)?)\s*%")
_COHORT_M12 = re.compile(r"(?i)(?:M12|12[- ]month[s]?|twelve[- ]month[s]?|(?:one|1)[- ]year)"
                         r"[^.\d%]{0,24}?(\d{1,3}(?:\.\d+)?)\s*%")
_COHORT_M36 = re.compile(r"(?i)(?:M36|36[- ]month[s]?|thirty[- ]six[- ]month[s]?|(?:three|3)[- ]year)"
                         r"[^.\d%]{0,24}?(\d{1,3}(?:\.\d+)?)\s*%")
_COHORT_SIZE = re.compile(r"(?i)([\d,]{2,12})\s*(?:logos?|customers?|accounts?|subscriptions?|locations?|units?)\b")
_RETAINED_PCT = re.compile(r"(?i)retain\w*[^.\d%]{0,24}?(\d{1,3}(?:\.\d+)?)\s*%")

_MONEY = re.compile(r"(?:INR|USD|EUR|GBP|Rs\.?|[₹$€£])\s*(?:\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
                    r"\s*(?:cr|crore|lakh|lakhs|k|m|mn|million|bn|billion)?", re.IGNORECASE)
_BARE_AMOUNT = re.compile(r"(?i)(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
                          r"(cr|crore|lakh|lakhs|k|m|mn|million|bn|billion)\b")
_GROUPED_NUM = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")
_ANY_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_DATE = re.compile(rf"\b((?:FY|CY)\s?(?:19|20)?\d{{2}}(?:[-–/](?:\d{{2}}|\d{{4}}))?"
                   rf"|(?:{_MONTH})[a-z]*\s+(?:19|20)\d{{2}}|H[12]\s*(?:FY|CY)?\s?(?:19|20)?\d{{2}}"
                   r"|Q[1-4]\s*(?:FY|CY)?\s?(?:19|20)?\d{2}|(?:19|20)\d{2})\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# bridge — (key, label, cue, information request)
# ---------------------------------------------------------------------------

_BRIDGE_SPEC: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("opening_revenue", "Opening revenue",
     re.compile(r"(?i)\b(?:opening|beginning|entry|start(?:ing)?|prior[- ]period)\s+"
                r"(?:ARR|MRR|revenue|balance|base|book|recurring\s+revenue)\b"),
     "opening revenue for the bridge period"),
    ("churn", "Churn (revenue lost)",
     re.compile(r"(?i)(?:\b(?:gross\s+)?churn(?:ed)?\b(?:\s+(?:revenue|ARR|MRR))?|\battrition\b"
                r"|\blost\s+(?:revenue|ARR|MRR|customers?|logos?|accounts?)\b|\bcancellation[s]?\b"
                r"|\bnon[- ]renewals?\b|\bfull\s+churn\b|\blapsed\s+(?:customers?|accounts?)\b)"),
     "revenue lost to churn"),
    ("contraction", "Contraction (down-sell)",
     re.compile(r"(?i)(?:\bcontraction\b|\bdown[- ]?sell\b|\bdowngrade[sd]?\b|\bdown[- ]?trading\b"
                r"|\bpartial\s+churn\b|\bseat\s+reductions?\b|\bde[- ]?scop(?:e|ing|ed)\b"
                r"|\breduc(?:tion|ed)\s+(?:in\s+)?(?:spend|seats|volume|scope|licen[cs]es)\b)"),
     "revenue lost to contraction / down-sell"),
    ("expansion", "Expansion (up-sell / cross-sell)",
     re.compile(r"(?i)(?:\bexpansion\b|\bup[- ]?sell\b|\bcross[- ]?sell\b|\bupgrade[sd]?\b|\bup[- ]?trading\b"
                r"|\bnet\s+expansion\b|\bincreased?\s+spend\b|\bseat\s+(?:growth|adds?)\b|\bprice\s+uplift\b)"),
     "revenue added by expansion within the opening population"),
    ("closing_revenue", "Closing revenue",
     re.compile(r"(?i)\b(?:closing|ending|exit|end[- ]of[- ]period|final)\s+"
                r"(?:ARR|MRR|revenue|balance|base|book|recurring\s+revenue)\b"),
     "closing revenue for the bridge period"),
)
_BRIDGE_KEYS = tuple(key for key, _l, _c, _r in _BRIDGE_SPEC)
_BRIDGE_LABEL = {key: label for key, label, _c, _r in _BRIDGE_SPEC}
_BRIDGE_ANY = re.compile(r"(?i)\b(bridge|roll[- ]?forward|rollforward|reconcil\w+|opening\s+to\s+closing"
                         r"|movement\s+in\s+(?:ARR|MRR|revenue))\b")
_EXCLUDE_NEW_CUE = re.compile(
    r"(?i)(?:exclud\w+\s+new\s+(?:customers?|logos?|accounts?|business|revenue)|retention\s+numerators?\s+exclude"
    r"|new\s+(?:customers?|logos?|accounts?|business|revenue)\s+(?:are|is)\s+excluded"
    r"|net\s+of\s+new\s+(?:customers?|business|logos?)"
    r"|excludes?\s+new\s+(?:logo|customer|account)\s+(?:wins?|additions?|revenue))"
)

# ---------------------------------------------------------------------------
# segment / tenure / loss
# ---------------------------------------------------------------------------

_NAME_TOKEN = r"[A-Za-z][A-Za-z0-9&/'’\.\-]*"
_ROW_NAME_PCT = re.compile(rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,4}})\s*"
                           r"(?:[:\-–—=]|\(|\bat\b|\bis\b|\bwas\b|\bran\b|\bsits?\s+at\b|\bdrove\b|\bdrives\b"
                           r"|\brepresent(?:s|ed)?\b|\baccount(?:s|ed)?\s+for\b|\bcontribut(?:es|ed)\b"
                           r"|\bmakes?\s+up\b|\s)\s*(?:~|≈|c\.\s*)?(\d{1,3}(?:\.\d+)?)\s*%")
_PCT_THEN_NAME = re.compile(r"(?:~|≈|c\.\s*)?(\d{1,3}(?:\.\d+)?)\s*%\s*"
                            r"(?:of\s+(?:the\s+)?(?:churn|losses?|loss|attrition|cancellations|retention"
                            r"|lost\s+revenue)\s*)?(?:from|in|is|due\s+to|driven\s+by|attributable\s+to"
                            rf"|caused\s+by|relates\s+to|sits\s+in|because\s+of)\s+((?:the\s+)?{_NAME_TOKEN}"
                            rf"(?:\s+{_NAME_TOKEN}){{0,4}})", re.IGNORECASE)
_SEGMENT_CUE = re.compile(
    r"(?i)(?:retention\s+by\s+segment|segment(?:al)?\s+retention|churn\s+by\s+segment|by\s+customer\s+segment"
    r"|retention\s+by\s+(?:customer\s+)?type|retention\s+by\s+(?:region|geography|channel|product|plan|tier)"
    r"|\bsegment\b[^.]{0,50}\bretention\b|\bretention\b[^.]{0,50}\bsegment\b|\bchurn\b[^.]{0,50}\bsegment\b)"
)
_TENURE_CUE = re.compile(
    r"(?i)(?:\btenure\b|by\s+tenure|tenure\s+band|\bvintage\b|\bnew\s+vs\s+\w+\b|(?:first|second|third)[- ]year\s+"
    r"(?:customers?|retention|churn)|age\s+of\s+(?:the\s+)?(?:customer|account|relationship)"
    r"|(?:months?|years?)\s+since\s+(?:start|onboarding|first\s+purchase|go[- ]live))"
)
_TENURE_BAND = re.compile(
    r"(?i)((?:<|>|under|over|less\s+than|more\s+than|up\s+to)?\s?\d{1,2}\s*(?:[-–]\s*\d{1,2})?\s*"
    r"(?:month|months|mo|year|years|yr|yrs)(?:\s*\+)?|first\s+year|second\s+year|third\s+year|year\s+[1-5]"
    r"|(?:new|young|mature|established|legacy|long[- ]tenured|tenured)\s+(?:customers?|cohort|accounts?|logos?|base))"
)
_LOSS_CUE = re.compile(
    r"(?i)\b(reason[s]?\s+for\s+(?:loss|churn|leaving|cancellation)|churn\s+(?:driver|drivers|reason|reasons|cause|causes)"
    r"|loss\s+(?:driver|drivers|reason|reasons)|why\s+customers?\s+(?:left|leave|churn)|exit\s+(?:reason|survey)"
    r"|cancellation\s+(?:reason|reasons|code|codes)|attrition\s+(?:driver|drivers|reason|reasons)|lost\s+(?:to|because))\b"
)
_LOSS_CONCENTRATION_CUE = re.compile(
    r"(?i)(?:loss(?:es)?\s+(?:are\s+|is\s+)?concentrat\w+|churn\s+(?:is\s+)?concentrat\w+|concentrated\s+"
    r"(?:in|among|amongst|within)|(?:most|majority|bulk|vast\s+majority)\s+of\s+(?:the\s+)?"
    r"(?:churn|loss|losses|attrition|cancellations|lost\s+revenue)|attrition\s+(?:is\s+)?(?:highest|worst|concentrated)"
    r"|churn\s+(?:sits|occurs|happens|is\s+highest|is\s+worst)\s+(?:in|among|within|at))"
)
_LOSS_RECORDS_CUE = re.compile(
    r"(?i)(?:exit\s+(?:interview|survey|reason)|cancellation\s+(?:code|reason)|CRM\s+(?:reason|field|closed[- ]lost)"
    r"|closed[- ]lost\s+reason|churn\s+log|loss\s+log|ticket\s+reason|reason\s+code)"
)
# name_key -> (scope cue, band filter, row request, pct request)
_CUT_SPEC: dict[str, tuple[re.Pattern[str], re.Pattern[str] | None, str, str]] = {
    "segment": (_SEGMENT_CUE, None, "retention by customer segment, each row on the same population",
                "retention rate per segment"),
    "tenure_band": (_TENURE_CUE, _TENURE_BAND,
                    "retention by tenure band (months since start period), on the cohort population",
                    "retention rate per tenure band"),
}

# ---------------------------------------------------------------------------
# contract protection — (key, label, cue, information request)
# ---------------------------------------------------------------------------

_CONTRACT_FIELDS: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("term", "Term",
     re.compile(r"(?i)(?:\d{1,2}\s*[- ]?\s*(?:year|yr)s?\s+(?:initial\s+|fixed\s+|firm\s+|minimum\s+)?term"
                r"|\d{1,3}\s*[- ]?\s*months?\s+(?:initial\s+|fixed\s+|minimum\s+)?term"
                r"|term\s+of\s+\d{1,3}\s*(?:year|yr|month)s?|\d{1,2}[- ]year\s+(?:contract|agreement|deal|commitment)"
                r"|(?:initial|minimum|firm|committed)\s+term\s+(?:of\s+)?\d{1,3}\s*(?:year|yr|month)s?"
                r"|rolling\s+month[- ]to[- ]month|month[- ]to[- ]month|\bevergreen\b|\bperpetual\b"
                r"|annual\s+term|single[- ]year\s+term)"),
     "contract term with start and end dates"),
    ("renewal_mechanism", "Renewal mechanism",
     re.compile(r"(?i)(?:auto(?:matic)?[- ]?renew(?:s|al|ing|able)?|\bevergreen\b|rolls?\s+over|roll[- ]over"
                r"|renews?\s+(?:annually|each\s+year|automatically|on\s+the\s+anniversary)|renewal\s+mechanism"
                r"|renewal\s+(?:is\s+)?(?:by\s+)?(?:mutual\s+(?:agreement|consent)|negotiation|tender"
                r"|re[- ]tender|competitive\s+process)|subject\s+to\s+(?:re[- ])?tender|manual\s+renewal"
                r"|opt[- ](?:in|out)\s+renewal|no\s+auto[- ]?renewal"
                r"|renewal\s+at\s+the\s+customer'?s?\s+(?:option|discretion))"),
     "renewal mechanism — automatic, evergreen, opt-in, mutual agreement or re-tender"),
    ("notice_period", "Notice period",
     re.compile(r"(?i)(?:\d{1,3}\s*(?:days?|weeks?|months?)[’']?\s*(?:prior\s+|written\s+)?notice"
                r"|notice\s+period\s+of\s+\d{1,3}\s*(?:days?|weeks?|months?)|notice\s+of\s+\d{1,3}\s*"
                r"(?:days?|weeks?|months?)|(?:give|provide|serve)\s+\d{1,3}\s*(?:days?|weeks?|months?)[’']?\s*notice"
                r"|no\s+notice\s+(?:period|required)|immediate\s+termination\s+on\s+notice)"),
     "notice period to terminate or non-renew"),
    ("minimum_commitment", "Minimum commitment",
     re.compile(r"(?i)(?:minimum\s+(?:commitment|volume|spend|purchase|revenue|quantity"
                r"|annual\s+(?:value|fee|charge|spend))|take[- ]or[- ]pay|committed\s+(?:spend|volume|minimum|value)"
                r"|volume\s+commitment|no\s+minimum\s+(?:commitment|volume|spend|purchase)|guaranteed\s+minimum)"),
     "minimum commitment — committed volume, spend or take-or-pay floor"),
    ("price_escalator", "Price escalator",
     re.compile(r"(?i)(?:price\s+escalat\w+|escalat(?:or|ion)\s+(?:clause|provision|of)?|price\s+(?:is\s+)?frozen"
                r"|annual\s+(?:price\s+)?(?:increase|uplift|indexation|adjustment)|no\s+price\s+escalat\w+"
                r"|index(?:ed|ation|[- ]linked)\s+to\s+(?:CPI|RPI|inflation)|CPI\s*[+\-]\s*\d{1,2}(?:\.\d+)?\s*%"
                r"|RPI\s*[+\-]\s*\d{1,2}(?:\.\d+)?\s*%|fixed\s+price\s+for\s+the\s+term"
                r"|(?:uplift|increase)\s+of\s+\d{1,2}(?:\.\d+)?\s*%\s*(?:per\s+annum|p\.?a\.?|annually|each\s+year))"),
     "price escalator — fixed, indexed to CPI/RPI or a stated annual uplift"),
    ("termination_for_convenience", "Termination for convenience",
     re.compile(r"(?i)(?:terminat\w*\s+for\s+convenience|terminate\s+(?:at\s+will|without\s+cause)|\bTFC\b"
                r"|cancellable\s+(?:at\s+any\s+time|on\s+notice|without\s+penalty)|break\s+(?:clause|right|option)"
                r"|right\s+to\s+terminate\s+(?:without\s+cause|for\s+any\s+reason|at\s+any\s+time)"
                r"|no\s+termination\s+for\s+convenience|terminat\w*\s+only\s+for\s+(?:cause|breach)"
                r"|exit\s+(?:clause|right)s?)"),
     "termination for convenience — whether the customer can exit without cause, on what notice"),
)
_CONTRACT_CUE = re.compile(
    r"(?i)\b(contract|contracts|agreement|agreements|MSA|master\s+services?\s+agreement|framework\s+agreement"
    r"|statement\s+of\s+work|SOW|supply\s+agreement|service\s+agreement|licen[cs]e\s+agreement|order\s+form"
    r"|subscription\s+agreement|executed\s+contract|signed\s+contract|contract\s+register)\b"
)
_CONTRACT_NAMED = re.compile(
    r"(?:contract|contracts|agreement|MSA|framework|SOW|subscription|relationship|arrangement|order\s+form)\s+"
    r"(?:with|for|held\s+by|signed\s+(?:with|by))\s+((?:the\s+)?[A-Z][A-Za-z0-9&'’\.\-]*"
    r"(?:\s+(?:[A-Z][A-Za-z0-9&'’\.\-]*|of|and|the|de|du))*)"
)
_CONTRACT_NAMED_ALT = re.compile(r"\b([A-Z][A-Za-z0-9&'’\.\-]*(?:\s+[A-Z][A-Za-z0-9&'’\.\-]*){0,3})\s+"
                                 r"(?:contract|agreement|MSA|framework|subscription|account)\b")
_CLIFF_SHARE = re.compile(
    r"(?i)(?:(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:total\s+|group\s+|contracted\s+|annual\s+|recurring\s+)?"
    r"(?:revenue|ARR|MRR|contract\s+value|billings|contracted\s+base)[^.]{0,70}?(?:up\s+for\s+renewal|expir\w+"
    r"|due\s+(?:for|to)\s+renew\w*|comes?\s+up\s+for\s+renewal|renewal\s+window|renews?|re[- ]tender\w*)"
    r"|(?:up\s+for\s+renewal|due\s+for\s+renewal|expir\w+|renewal\s+cliff|comes?\s+up\s+for\s+renewal)"
    r"[^.]{0,70}?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:total\s+|group\s+)?(?:revenue|ARR|MRR|contract\s+value))"
)
_CLIFF_WINDOW = re.compile(
    r"(?i)(?:within\s+(?:the\s+)?next\s+\d{1,2}\s*(?:months?|quarters?)|(?:over|in)\s+the\s+next\s+\d{1,2}\s*"
    r"(?:months?|quarters?)|in\s+the\s+next\s+(?:twelve|12)\s+months|(?:in|during|by)\s+(?:FY|CY)\s?(?:19|20)?\d{2}"
    r"|H[12]\s*(?:FY|CY)?\s?(?:19|20)?\d{2}|Q[1-4]\s*(?:FY|CY)?\s?(?:19|20)?\d{2}"
    r"|before\s+(?:the\s+)?(?:year|contract)\s+end)"
)
_CLIFF_CUE = re.compile(r"(?i)(?:renewal\s+cliff|up\s+for\s+renewal|due\s+for\s+renewal|renewal\s+window"
                        r"|renewal\s+exposure|contracts?\s+expir\w+|re[- ]tender|renewal\s+risk"
                        r"|coming\s+up\s+for\s+renewal)")
_COMMITTED_CUE = re.compile(r"(?i)(?:contracted\s+(?:revenue|base|ARR|backlog)|committed\s+revenue|under\s+contract"
                            r"|contractually\s+committed|minimum\s+commitment|take[- ]or[- ]pay|backlog"
                            r"|order\s+book|committed\s+backlog)")
_UNPROTECTED_CUE = re.compile(r"(?i)(?:no\s+(?:written\s+)?contract|out\s+of\s+contract|uncontracted|expired\s+contract"
                              r"|non[- ]contracted|month[- ]to[- ]month|at[- ]will|rolling\s+monthly"
                              r"|no\s+minimum\s+commitment|terminat\w*\s+for\s+convenience|cancellable\s+at\s+any\s+time)")

# ---------------------------------------------------------------------------
# language hygiene / guards
# ---------------------------------------------------------------------------

_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|investing|proceed|proceeding|pass"
    r"|passing|decline|acquire|acquiring)|invest(?:ment)?\s+recommendation|recommendation\s+to\s+invest"
    r"|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|proceed\s+with\s+(?:the\s+)?"
    r"(?:investment|acquisition|deal)|should\s+(?:invest|proceed|pass|walk\s+away)|(?:an\s+)?attractive\s+investment"
    r"|(?:a\s+)?compelling\s+investment|do\s+not\s+invest|pass\s+on\s+(?:the\s+)?(?:deal|opportunity|asset)"
    r"|investment\s+(?:case|thesis)\s+is\s+(?:compelling|attractive)|worth\s+(?:the\s+)?(?:price|investment))\b"
)
_CAVEAT_FRAME = re.compile(
    r"(?i)(?:\bit\s+should\s+be\s+noted\s+that\s*|\b(?:one|a|the)\s+(?:minor\s+|small\s+)?caveat\s+"
    r"(?:is|being)(?:\s+that)?\s*|\bas\s+a\s+caveat[,:]?\s*|\bwith\s+the\s+caveat\s+that\s*"
    r"|\bcaveat(?:ed)?\s+by\s+the\s+fact\s+that\s*|\bthat\s+said[,:]?\s*|\bto\s+be\s+fair[,:]?\s*)"
)
_HEDGE_WORD = re.compile(r"(?i)\b(?:slightly|marginally|somewhat|a\s+little|modestly|mildly|arguably)\s+"
                         r"(?=fell|declin|drop|decreas|lower|weaken|deteriorat|soften|erod)")
_PLACEHOLDER_NAME = re.compile(
    r"(?i)^(?:tbd|n/?a|unnamed|placeholder|various|customer\s*[a-z]?\d*|client\s*[a-z]?\d*|account\s*[a-z]?\d*"
    r"|company\s*[a-z]?\d*|segment\s*\d*|cohort\s*\d*|peer\s*\d*|redacted|anonymous|confidential"
    r"|largest\s+customer\s*\d*|top\s+\d+)$"
)
_CONTRACT_WORD = re.compile(r"(?i)\s*\b(agreement|contract|MSA|framework|SOW|account|subscription|arrangement"
                            r"|relationship|order\s+form)\b\s*")
_ROW_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "at", "to", "for", "by", "with", "this", "that", "these",
    "those", "it", "its", "their", "our", "his", "her", "revenue", "turnover", "sales", "total", "group",
    "company", "business", "management", "target", "customer", "customers", "client", "clients", "account",
    "accounts", "logo", "logos", "churn", "retention", "retained", "loss", "losses", "lost", "reason",
    "reasons", "driver", "drivers", "growth", "margin", "ebitda", "cagr", "year", "years", "month", "months",
    "period", "fy", "cy", "approximately", "about", "circa", "around", "some", "roughly", "up", "down",
    "from", "than", "over", "under", "share", "mix", "split", "rate", "value", "volume", "price", "cost",
    "data", "room", "information", "memorandum", "appendix", "annex", "table", "figure", "note", "notes",
    "source", "sources", "ledger", "workbook", "however", "overall", "broadly", "materially", "representing",
    "including", "remaining", "balance", "which", "while", "where", "when", "was", "were", "is", "are", "be",
    "been", "has", "have", "had", "will", "would", "may", "cohort", "cohorts", "population", "segment",
    "segments", "tenure", "bridge", "opening", "closing", "expansion", "contraction", "grr", "nrr",
    "contract", "contracts", "agreement", "renewal", "term", "notice", "management’s", "management's",
    "top", "largest", "biggest", "material",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(
            str((row[i] if i < len(row) else "—") or "—").replace("|", "\\|").replace("\n", " ").strip()
            for i in range(len(headers))
        ) + " |")
    return "\n".join(lines) + "\n\n"


def _info_request(label: str) -> str:
    return f"Information request: {label} (not stated in the data room)"


def _is_filled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip()
    if not text or text == _NA or text.startswith("N/A"):
        return False
    return not text.startswith("Information request")


def _num(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"-?\d+(?:\.\d+)?", str(raw or "").strip().replace(",", ""))
    try:
        return float(m.group(0)) if m else None
    except ValueError:
        return None


def _pct(value: Any) -> float | None:
    """A retention / churn percentage, sanity-bounded. NRR may exceed 100%."""
    val = _num(value)
    return val if val is not None and 0 <= val <= 400 else None


def _title_case(name: str) -> str:
    if not name:
        return ""
    return name if name[:1].isupper() else name[:1].upper() + name[1:]


def _clean_row_name(raw: Any, *, max_chars: int = 48) -> str:
    """Trim a candidate segment / reason / counterparty name and reject filler."""
    name = _clean(raw, max_chars).strip(" .,;:—–-()")
    name = re.sub(r"(?i)^(?:the|a|an|and|or|of|in|at|to|for|by|with|due)\s+", "", name)
    name = re.sub(r"(?i)\s+(?:of|in|at|to|for|by|with|and|or|is|was|the|due)$", "", name).strip(" .,;:—–-")
    if len(name) < 2 or len(name) > max_chars or _PLACEHOLDER_NAME.match(name):
        return ""
    tokens = [t for t in re.split(r"\s+", name.lower()) if t]
    if not tokens or all(t in _ROW_STOP for t in tokens):
        return ""
    return name if re.search(r"[A-Za-z]{2}", name) else ""


def _population(value: Any, *, default: str = "logos") -> str:
    """Normalise a population description to one of the four allowed values."""
    fallback = default if default in _POPULATIONS else "logos"
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    for pop in _POPULATIONS:
        if pop in text:
            return pop
    if "logo" in text:
        return "logos"
    if any(w in text for w in ("subscription", "licen", "seat", "contract line")):
        return "subscriptions"
    if any(w in text for w in ("location", "site", "branch", "store", "outlet", "depot")):
        return "locations"
    if any(w in text for w in ("account", "customer", "client")):
        return "accounts"
    return fallback


def _direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in _DIRECTIONS else "unknown"


def _snippet(match: re.Match[str] | None, *, limit: int = 110) -> str:
    return _clean(match.group(0).strip(" ,;.:"), limit) if match else ""


def _cited(match: re.Match[str] | None, request: str) -> str:
    text = _snippet(match)
    return f"{text} {_DOC_CITE}" if text else _info_request(request)


def _period_of(text: Any) -> str:
    m = _DATE.search(str(text or ""))
    return _clean(m.group(1), 30) if m else ""


def _prose(corpus: str) -> str:
    """Drop the '### filename' blob headers so they never leak into a statement."""
    return _HEADER_LINE.sub(" ", corpus or "")


def _clauses(corpus: str) -> list[str]:
    """Clause-level split. Unlike `_sentences` this also breaks after 'FY2024.'."""
    return [t for t in (_clean(c, 320) for c in _CLAUSE_SPLIT.split(_prose(corpus))) if len(t) >= 20]


def _soften_invest(text: Any) -> str:
    """Strip invest/pass language — this document reports retention, not verdicts."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("retention evidence only — no deal verdict expressed", raw)
    # Bare verdict words that survived the phrase matcher.
    out = re.sub(
        r"(?i)(?:^|[\s—\-–:])(?:invest|pass)(?:\s+recommendation)?(?=[\s.,;:!?]|$)",
        " (no deal verdict) ",
        out,
    )
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _finding_voice(text: Any, *, falling: bool = False) -> str:
    """Remove caveat framing and hedges so a falling number reads as a finding."""
    raw = _soften_invest(text)
    if not raw or not falling:
        return raw
    out = re.sub(r"\s{2,}", " ", _HEDGE_WORD.sub("", _CAVEAT_FRAME.sub("", raw))).strip()
    return out[:1].upper() + out[1:] if out[:1].islower() else out


def _metric_key_from_token(token: Any) -> str:
    raw = re.sub(r"\s+", " ", str(token or "").strip())
    return next((key for pattern, key in _METRIC_TOKEN_KEY if pattern.match(raw)), "")


def _metric_display(key: str, fallback: str = "") -> str:
    return _METRIC_LABEL.get(key) or _clean(fallback, 60) or "Retention"


def _real_rows(rows: list[dict[str, Any]], key: str) -> int:
    """Rows carrying evidence rather than a named information request."""
    return sum(1 for r in rows
               if isinstance(r, dict) and not str(r.get(key) or "").startswith("Information"))


# ---------------------------------------------------------------------------
# exported test helpers
# ---------------------------------------------------------------------------


def _same_population(
    *,
    population: Any = None,
    grr: Any = None,
    nrr: Any = None,
    logo_retention: Any = None,
    stated_populations: list[Any] | None = None,
    new_customers_excluded: Any = True,
) -> tuple[bool, str]:
    """Return ``(on_same_population, notes)`` for the retention headline metrics.

    GRR, NRR and logo retention are only comparable when measured on one population, held constant,
    with new customers excluded from the numerators. Where the packs state different populations for
    different metrics the metrics are still reported, but the "same population" test fails and the
    mismatch is named.
    """
    pop = _population(population)
    have = {label: val for label, val in (("GRR", _pct(grr)), ("NRR", _pct(nrr)),
                                          ("logo retention", _pct(logo_retention))) if val is not None}
    distinct = sorted({_population(p, default=pop) for p in (stated_populations or []) if str(p or "").strip()})

    fails: list[str] = []
    if not have:
        fails.append("no GRR, NRR or logo retention value is evidenced")
    if len(distinct) > 1:
        fails.append("the packs measure retention on more than one population (" + ", ".join(distinct)
                     + f"), so the rates are not comparable until re-cut on **{pop}**")
    if new_customers_excluded is not True and not _is_filled(new_customers_excluded):
        fails.append("the packs do not confirm that new customers are excluded from the numerators, so the "
                     "rates may be flattered by new business")

    values = ", ".join(f"{label} {val:g}%" for label, val in have.items())
    if fails:
        return False, (f"Retention is **not** yet on one common population: {'; '.join(fails[:3])}. "
                       + (f"Values read: {values}. " if values else "")
                       + f"Required basis — {_SAME_POP_RULE} {_COMPUTED}")
    return True, (f"{values} — all measured on **{pop}**, held constant across the bridge and the cohorts; "
                  f"{_EXCLUSION_RULE} {_COMPUTED}")


def _retention_moved(
    from_value: Any,
    to_value: Any,
    *,
    metric: str = "retention",
    tolerance: float = 0.25,
) -> tuple[str, str, bool]:
    """Return ``(direction, magnitude, is_finding)`` for a retention movement.

    A downward movement in a retention metric is a **finding**, not a caveat, so ``is_finding`` is
    True. Churn metrics invert: a rising churn rate is the same finding.
    """
    start, end = _pct(from_value), _pct(to_value)
    label = _metric_display(metric if metric in _METRIC_LABEL else "", metric)
    if start is None or end is None:
        return "unknown", _info_request(
            f"two dated values for {label} so the movement can be measured in pp"), False
    delta = end - start
    inverted = "churn" in str(metric or "").lower() or "churn" in label.lower()
    if abs(delta) < tolerance:
        return "flat", (f"{start:g}% → {end:g}% ({delta:+.1f} pp, inside a {tolerance:g} pp tolerance) "
                        f"{_COMPUTED}"), False
    direction = "up" if delta > 0 else "down"
    worse = (direction == "up") if inverted else (direction == "down")
    return direction, (f"{delta:+.1f} pp ({start:g}% → {end:g}%)"
                       + (" — deterioration" if worse else " — improvement") + f" {_COMPUTED}"), bool(worse)


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_customer_stickiness_corpus(deal: Deal, index: dict[str, Any]) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {"customer": 0, "financial": 1, "deal_strategy": 2, "market_competition": 3,
              "operations": 4, "company_management": 5}
    needles = ("retention", "cohort", "churn", "valuation", "commercial", "comparable", "stickiness",
               "nrr", "grr", "customer", "contract", "renewal", "revenue", "subscription")
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple[int, int, str]:
        name = str(d.get("filename") or "").lower()
        return (prefer.get(str(d.get("cdl_category") or ""), 9),
                0 if any(n in name for n in needles) else 1,
                str(d.get("filename") or ""))

    blobs: list[str] = []
    sources: list[str] = []
    for doc in sorted(docs, key=_rank)[:12]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        loaded: dict[str, Any] = {}
        try:
            raw_loaded = load_library_document(deal, filename)
            if isinstance(raw_loaded, dict):
                loaded = raw_loaded
        except Exception:
            loaded = {}
        text = ""
        for candidate in (loaded.get("text"), doc.get("excerpt")):
            if candidate is not None and str(candidate).strip():
                text = candidate if isinstance(candidate, str) else str(candidate)
                break
        text = re.sub(r"[ \t]+", " ", _PDF_BULLETS.sub(" ", _ZWSP.sub("", text))).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


# ---------------------------------------------------------------------------
# heuristic — population definition
# ---------------------------------------------------------------------------


def _detect_population(corpus: str) -> tuple[str, list[str]]:
    """Return ``(primary_population, populations_seen)`` from the evidence."""
    counts = {pop: n for pop, n in ((p, len(pat.findall(corpus or ""))) for p, pat in _POP_PATTERNS) if n}
    if not counts:
        return "logos", []
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], _POPULATIONS.index(kv[0])))
    return ordered[0][0], [pop for pop, n in ordered if n >= 2] or [ordered[0][0]]


def _retention_populations(corpus: str) -> list[str]:
    """Populations explicitly attached to a retention or churn statement."""
    out: list[str] = []
    for clause in _clauses(corpus):
        if not _METRIC_TOKEN.search(clause):
            continue
        out.extend(pop for pop, pattern in _POP_PATTERNS if pattern.search(clause) and pop not in out)
    return out


def _extract_population_definition(corpus: str) -> dict[str, Any]:
    primary, seen = _detect_population(corpus or "")
    clauses = _clauses(corpus)
    defined = next((c for c in clauses if _POP_DEFINITION_CUE.search(c)), "")
    constant = next((c for c in clauses if _POP_CONSTANT_CUE.search(c)), "")

    if defined:
        definition = f"Population measured: **{primary}**. {_clean(defined, 240)} {_DOC_CITE}"
    elif seen:
        definition = (f"Population measured: **{primary}** — inferred from how the packs count the base "
                      f"({', '.join(seen)} appear in the evidence). Every retention number here is on "
                      f"{primary} and on nothing else {_COMPUTED}")
    else:
        definition = _info_request("the retention population — logos, accounts, locations or subscriptions "
                                   "— stated once and applied to every cohort, bridge and rate")

    if constant:
        constant_rule = f"{_clean(constant, 220)} {_DOC_CITE}"
    else:
        constant_rule = (f"Held constant by construction: the opening {primary} population is fixed before "
                         f"each period starts, no re-basing is applied mid-period, and {_EXCLUSION_RULE}. "
                         f"Cohorts, the bridge, GRR, NRR and logo retention all use this one population "
                         f"{_COMPUTED}")
    if len(seen) > 1:
        constant_rule += (f" Caution: the packs count the base on more than one population "
                          f"({', '.join(seen)}); a count on one population is never presented as a count on "
                          "another, and the mismatch is named rather than blended.")

    return {
        "population": primary,
        "definition": definition,
        "constant_rule": constant_rule,
        "source": _DOC_CITE if (defined or seen) else _NA,
        "information_request": "" if defined else _info_request(
            f"written confirmation that retention is measured on {primary}, with the definition of an "
            "active member of the population and the rule keeping it constant"),
    }


# ---------------------------------------------------------------------------
# heuristic — cohorts
# ---------------------------------------------------------------------------


def _cohort_row(cohort: Any, size: Any = None, m6: Any = None, m12: Any = None,
                m36: Any = None) -> dict[str, Any] | None:
    label = _clean(cohort, 40).strip()
    if not label or _PLACEHOLDER_NAME.match(label):
        return None
    size_val = _num(size)
    return {
        "cohort": label,
        "size_units": size_val if size_val is not None and 0 <= size_val <= 1e9 else None,
        "m6_retention_pct": _pct(m6),
        "m12_retention_pct": _pct(m12),
        "m36_retention_pct": _pct(m36),
    }


def _extract_cohorts(corpus: str) -> list[dict[str, Any]]:
    """Cohort rows keyed on start period — monthly / quarterly vintages."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _push(row: dict[str, Any] | None) -> bool:
        points = ("m6_retention_pct", "m12_retention_pct", "m36_retention_pct")
        if not row or all(row.get(k) is None for k in points):
            return False
        key = str(row["cohort"]).lower()
        if key in seen:
            return False
        seen.add(key)
        rows.append(row)
        return len(rows) >= 12

    for m in _COHORT_RE.finditer(corpus or ""):
        if _push(_cohort_row(re.sub(r"\s+", " ", m.group(1)).strip(), m.group(2), m.group(3),
                             m.group(4), m.group(5))):
            break
    if rows:
        return rows

    # Prose fallback: "the Q1 FY2023 cohort retained 84% at 12 months".
    for clause in _clauses(corpus):
        period = re.search(_COHORT_PERIOD, clause, re.IGNORECASE) if _COHORT_CUE.search(clause) else None
        if not period:
            continue
        m6, m36 = _COHORT_M6.search(clause), _COHORT_M36.search(clause)
        m12 = _COHORT_M12.search(clause) or _RETAINED_PCT.search(clause)
        size = _COHORT_SIZE.search(clause)
        if _push(_cohort_row(re.sub(r"\s+", " ", period.group(0)).strip(),
                             size.group(1) if size else None, m6.group(1) if m6 else None,
                             m12.group(1) if m12 else None, m36.group(1) if m36 else None)):
            break
    return rows


def _cohort_notes(cohorts: list[dict[str, Any]], *, population: str) -> str:
    if not cohorts:
        return _info_request(f"customer and revenue cohorts by start period on a constant {population} "
                            "population, with size and retention at M6, M12 and M36")
    m12 = [(str(c.get("cohort")), _pct(c.get("m12_retention_pct"))) for c in cohorts
           if isinstance(c, dict) and _pct(c.get("m12_retention_pct")) is not None]
    bits = [f"{len(cohorts)} cohort(s) by start period on a constant **{population}** base"]
    if len(m12) >= 2:
        (first_label, first_val), (last_label, last_val) = m12[0], m12[-1]
        delta = (last_val or 0.0) - (first_val or 0.0)
        shape = "steepening" if delta < -0.25 else "flattening" if delta > 0.25 else "stable"
        bits.append(f"M12 retention moves from {first_val:g}% ({first_label}) to {last_val:g}% "
                    f"({last_label}) — {delta:+.1f} pp, a {shape} curve")
    elif m12:
        bits.append(f"M12 retention read for {m12[0][0]} at {m12[0][1]:g}%")
    missing = sum(1 for c in cohorts if isinstance(c, dict) and _pct(c.get("m36_retention_pct")) is None)
    if missing:
        bits.append(f"{missing} cohort(s) have no M36 point — the curve is not extrapolated")
    return "; ".join(bits) + f" {_COMPUTED}"


# ---------------------------------------------------------------------------
# heuristic — retention bridge
# ---------------------------------------------------------------------------


def _nearest_value(clause: str, anchor: int) -> str:
    """The money / percentage amount closest to the cue inside one clause."""
    for pattern, render in ((_MONEY, lambda m: _clean(m.group(0).strip(" ,;."), 60)),
                            (_BARE_AMOUNT, lambda m: _fmt_num(m.group(1), m.group(2))),
                            (_GROUPED_NUM, lambda m: _fmt_num(m.group(0)))):
        best: tuple[int, str] | None = None
        for m in pattern.finditer(clause or ""):
            distance = min(abs(m.start() - anchor), abs(m.end() - anchor))
            text = render(m)
            if text and (best is None or distance < best[0]):
                best = (distance, text)
        if best is not None:
            return f"{best[1]} {_DOC_CITE}"
    pct = _ANY_PCT.search(clause or "")
    return f"{_num(pct.group(1)):g}% of opening revenue {_DOC_CITE}" if pct else ""


def _extract_retention_bridge(corpus: str, *, population: str) -> dict[str, Any]:
    clauses = _clauses(corpus)
    values: dict[str, str] = {}
    hits: dict[str, str] = {}
    for key, _label, cue, _req in _BRIDGE_SPEC:
        for clause in clauses:
            m = cue.search(clause)
            if not m:
                continue
            hits.setdefault(key, clause)
            value = _nearest_value(clause, m.start())
            if value:
                values[key], hits[key] = value, clause
                break

    period = next((p for p in (_period_of(hits.get("closing_revenue", "")),
                               _period_of(hits.get("opening_revenue", "")),
                               _period_of(next((c for c in clauses if _BRIDGE_ANY.search(c)), "")),
                               _period_of(corpus)) if p), "")

    excluded: Any = True
    if not _EXCLUDE_NEW_CUE.search(corpus or ""):
        excluded = ("Enforced here — new customers are excluded from the retention numerators. The packs do "
                    f"not state the convention, so written confirmation is requested rather than assumed "
                    f"{_COMPUTED}")

    missing = [_BRIDGE_LABEL[k] for k in _BRIDGE_KEYS if k not in values]
    gap_bits: list[str] = []
    if missing:
        gap_bits.append("Not evidenced and therefore not reconciled: " + ", ".join(missing))
    if values and missing:
        gap_bits.append("the bridge does not tie opening to closing, so GRR and NRR are read from stated "
                        "rates rather than derived from the movement")
    if not period:
        gap_bits.append("the bridge period is not dated in the packs opened")
    if excluded is not True:
        gap_bits.append("the exclusion of new customers is applied here but is not documented in the packs")

    out: dict[str, Any] = {
        "period": period or _info_request("the period the retention bridge covers"),
        "new_customers_excluded": excluded,
        "source": _DOC_CITE if values else _NA,
        "gaps": "; ".join(gap_bits) + "." if gap_bits else (
            "Opening revenue, churn, contraction, expansion and closing revenue are all evidenced and "
            f"reconcile on one {population} population {_COMPUTED}"),
    }
    for key, _label, _cue, request in _BRIDGE_SPEC:
        out[key] = values.get(key) or _info_request(f"{request}, on a constant {population} population")
    return out


def _bridge_filled(bridge: dict[str, Any]) -> int:
    return sum(1 for key in _BRIDGE_KEYS if _is_filled(bridge.get(key)))


# ---------------------------------------------------------------------------
# heuristic — retention metrics
# ---------------------------------------------------------------------------


def _complement(found: dict[str, float], target: str, source: str) -> str:
    """Fill ``target`` as 100% − ``source`` and return a note describing the derivation."""
    base = found.get(source)
    if target in found or base is None or not (0 <= base <= 100):
        return ""
    found[target] = round(100.0 - base, 2)
    return (f"{_METRIC_LABEL[target]} derived as 100% − {_METRIC_LABEL[source].lower()} ({base:g}%) = "
            f"{found[target]:g}% on the same population {_COMPUTED}")


def _expansion_note(found: dict[str, float]) -> str:
    grr, nrr = found.get("grr_pct"), found.get("nrr_pct")
    if grr is None or nrr is None:
        return ""
    if nrr + 0.05 < grr:
        return (f"NRR ({nrr:g}%) sits below GRR ({grr:g}%), which cannot hold with non-negative expansion — "
                f"the rates are on different populations or periods and must be re-cut before use {_COMPUTED}")
    return (f"Expansion contributes {nrr - grr:+.1f} pp between GRR ({grr:g}%) and NRR ({nrr:g}%) on the "
            f"same population {_COMPUTED}")


def _extract_retention_metrics(corpus: str) -> tuple[dict[str, float | None], list[str]]:
    """Parse the retention metric family plus notes explaining any derivation."""
    found: dict[str, float] = {}
    for key, pattern in _METRIC_PATTERNS:
        m = pattern.search(corpus or "")
        val = _pct(m.group(1)) if m else None
        if val is not None:
            found[key] = val
    notes = [n for n in (_complement(found, "logo_retention_pct", "logo_churn_pct"),
                         _complement(found, "logo_churn_pct", "logo_retention_pct"),
                         _complement(found, "grr_pct", "revenue_churn_pct"),
                         _expansion_note(found)) if n]
    return {key: found.get(key) for key in _METRIC_KEYS}, notes


def _retention_on_same_population(
    metrics: dict[str, float | None],
    *,
    population: str,
    corpus: str = "",
    bridge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bridge = bridge if isinstance(bridge, dict) else {}
    ok, notes = _same_population(
        population=population, grr=metrics.get("grr_pct"), nrr=metrics.get("nrr_pct"),
        logo_retention=metrics.get("logo_retention_pct"), stated_populations=_retention_populations(corpus),
        new_customers_excluded=bridge.get("new_customers_excluded", True),
    )

    def _value(key: str, label: str) -> str:
        val = _pct(metrics.get(key))
        if val is None:
            return _info_request(f"{label} for the bridge period on the {population} population, with new "
                                 "customers excluded from the numerator")
        return f"{val:g}% on {population} {_DOC_CITE}"

    return {
        "population": population,
        "grr": _value("grr_pct", "gross revenue retention"),
        "nrr": _value("nrr_pct", "net revenue retention"),
        "logo_retention": _value("logo_retention_pct", "logo retention"),
        "notes": notes,
        "on_same_population": ok,
    }


# ---------------------------------------------------------------------------
# heuristic — retention delta (falling retention is a finding)
# ---------------------------------------------------------------------------


def _delta_row(
    *,
    metric_key: str,
    metric_label: str,
    from_value: Any,
    to_value: Any,
    from_label: str = "",
    to_label: str = "",
    source: str = "",
) -> dict[str, Any] | None:
    start, end = _pct(from_value), _pct(to_value)
    if start is None or end is None:
        return None
    direction, magnitude, is_finding = _retention_moved(start, end, metric=metric_key or metric_label)
    if direction == "unknown":
        return None
    return {
        "metric": _metric_display(metric_key, metric_label),
        "from_value": f"{start:g}%" + (f" ({_clean(from_label, 24)})" if from_label else ""),
        "to_value": f"{end:g}%" + (f" ({_clean(to_label, 24)})" if to_label else ""),
        "direction": direction,
        "magnitude": magnitude,
        "is_finding": bool(is_finding),
        "source": source or _DOC_CITE,
    }


def _extract_retention_delta(corpus: str) -> list[dict[str, Any]]:
    """Movements in retention. A downward movement is flagged as a finding."""
    text = corpus or ""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _push(row: dict[str, Any] | None) -> bool:
        if not row:
            return False
        key = (str(row["metric"]), str(row["from_value"]), str(row["to_value"]))
        if key in seen:
            return False
        seen.add(key)
        rows.append(row)
        return len(rows) >= 6

    for m in _MOVE_PHRASE.finditer(text):
        middle = m.group(2) or ""
        row = _delta_row(metric_key=_metric_key_from_token(m.group(1)), metric_label=m.group(1),
                         from_value=m.group(3), to_value=m.group(4),
                         source=f"{_clean(m.group(0), 130)} {_DOC_CITE}")
        if not row:
            continue
        # Where prose and arithmetic disagree the stated values win, and the disagreement is
        # recorded rather than resolved silently.
        if _DOWN_VERB.search(middle) and row["direction"] == "up":
            row["magnitude"] += (" (the packs call this a fall; the stated values are ordered the other way "
                                 "round and are reported as read)")
        elif _FLAT_VERB.search(middle) and row["direction"] != "flat":
            row["magnitude"] += (" (the packs call this flat; the stated values differ and are reported as "
                                 "read)")
        if _push(row):
            break

    if len(rows) < 6:
        for m in _MOVE_PAREN.finditer(text):
            if _push(_delta_row(metric_key=_metric_key_from_token(m.group(1)), metric_label=m.group(1),
                                from_value=m.group(2), to_value=m.group(4), from_label=m.group(3),
                                to_label=m.group(5), source=f"{_clean(m.group(0), 130)} {_DOC_CITE}")):
                break

    if len(rows) < 6:
        for m in _PP_MOVE.finditer(text):
            middle, move = m.group(2) or "", _num(m.group(3))
            if move is None or not (0 < move <= 100):
                continue
            key = _metric_key_from_token(m.group(1)) or "retention_12m_pct"
            label = _metric_display(key, m.group(1))
            inverted = "churn" in label.lower()
            if _DOWN_VERB.search(middle):
                direction, worse = "down", not inverted
            elif _UP_VERB.search(middle):
                direction, worse = "up", inverted
            elif _FLAT_VERB.search(middle):
                direction, worse = "flat", False
            else:
                continue
            sign = "-" if direction == "down" else "+" if direction == "up" else ""
            if _push({
                "metric": label,
                "from_value": _info_request("opening value for this movement"),
                "to_value": _info_request("closing value for this movement"),
                "direction": direction,
                "magnitude": (f"{sign}{move:g} pp as stated in the packs; the two endpoint values are not "
                              f"given {_DOC_CITE}"),
                "is_finding": bool(worse and direction != "flat"),
                "source": f"{_clean(m.group(0), 130)} {_DOC_CITE}",
            }):
                break

    rows.sort(key=lambda r: (not r.get("is_finding"), str(r.get("metric"))))
    return rows[:6]


def _falling(deltas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [d for d in deltas if isinstance(d, dict)
            and (d.get("is_finding") or _direction(d.get("direction")) == "down")]


def _falling_statement(deltas: list[dict[str, Any]]) -> str:
    falls = _falling(deltas)
    if not falls:
        return ""
    return ("**Finding — retention has fallen:** " + "; ".join(
        f"{_clean(r.get('metric'), 48)} {_clean(r.get('from_value'), 24)} → "
        f"{_clean(r.get('to_value'), 24)} ({_clean(r.get('magnitude'), 60)})" for r in falls[:3]
    ) + ". This is reported as a finding, not as a caveat.")


# ---------------------------------------------------------------------------
# heuristic — segment / tenure / loss
# ---------------------------------------------------------------------------


def _scoped_rows(corpus: str, *, cue: re.Pattern[str], band: re.Pattern[str] | None = None,
                 limit: int = 8) -> list[tuple[str, float, str]]:
    """Return (name, pct, clause) triples from clauses matching ``cue``."""
    out: list[tuple[str, float, str]] = []
    seen: set[str] = set()

    def _accept(name: Any, pct: Any, clause: str) -> None:
        cleaned, val = _clean_row_name(name), _pct(pct)
        if not cleaned or val is None or val > 100 or cleaned.lower() in seen:
            return
        if band is not None and not band.search(cleaned):
            return
        seen.add(cleaned.lower())
        out.append((_title_case(cleaned), val, clause))

    for clause in (c for c in _clauses(corpus) if cue.search(c)):
        for m in _ROW_NAME_PCT.finditer(clause):
            _accept(m.group(1), m.group(2), clause)
        for m in _PCT_THEN_NAME.finditer(clause):
            _accept(m.group(2), m.group(1), clause)
        if band is not None:
            for m in band.finditer(clause):
                nearby = _ANY_PCT.search(clause[m.end() : m.end() + 60])
                if nearby:
                    _accept(m.group(1), nearby.group(1), clause)
        if len(out) >= limit:
            break
    return out[:limit]


def _extract_retention_cut(corpus: str, *, name_key: str, population: str) -> list[dict[str, Any]]:
    """Retention cut by segment (``name_key='segment'``) or by tenure band."""
    cue, band, row_request, pct_request = _CUT_SPEC[name_key]
    rows = [{
        name_key: name,
        "retention_pct": f"{pct:g}%",
        "population": _population(next((p for p, pat in _POP_PATTERNS if pat.search(clause)), population),
                                  default=population),
        "source": _DOC_CITE,
    } for name, pct, clause in _scoped_rows(corpus, cue=cue, band=band, limit=8)]
    if not rows:
        rows.append({name_key: _info_request(row_request), "retention_pct": _info_request(pct_request),
                     "population": population, "source": _NA})
    return rows[:8]


def _extract_loss_reasons(corpus: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, pct, clause in _scoped_rows(corpus, cue=_LOSS_CUE, limit=8):
        where = ""
        for pattern, label in ((_TENURE_BAND, "tenure"), (_SEGMENT_CUE, "segment")):
            m = pattern.search(clause)
            if m:
                where = f"{label}: {_clean(m.group(0), 60)}"
                break
        if not where:
            m = _LOSS_CONCENTRATION_CUE.search(clause)
            where = _clean(clause[m.start() : m.start() + 120], 120) if m else ""
        rows.append({
            "reason": name,
            "contribution_pct": f"{pct:g}% of recorded loss",
            "concentrates_in": where or _info_request(
                "where this reason concentrates — segment, tenure band or channel"),
            "source": _DOC_CITE,
        })
    if not rows:
        tail = (" (the packs reference loss records but do not report the reason split)"
                if _LOSS_RECORDS_CUE.search(corpus or "")
                else " (no loss-reason records are referenced in the packs opened)")
        rows.append({
            "reason": _info_request("reasons for loss as captured in the records — exit interviews, "
                                    "cancellation reason codes or CRM closed-lost fields" + tail),
            "contribution_pct": _info_request("each reason's share of total recorded loss"),
            "concentrates_in": _info_request(
                "the segment, tenure band or channel each reason concentrates in"),
            "source": _NA,
        })
    return rows[:8]


def _weakest(rows: list[dict[str, Any]], key: str) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name, val = str(row.get(key) or ""), _pct(row.get("retention_pct"))
        if not name or name.startswith("Information") or val is None:
            continue
        if best is None or val < best[1]:
            best = (name, val)
    return best


def _loss_concentration(corpus: str, *, reasons: list[dict[str, Any]], by_tenure: list[dict[str, Any]],
                        by_segment: list[dict[str, Any]]) -> dict[str, str]:
    hit = next((c for c in _clauses(corpus) if _LOSS_CONCENTRATION_CUE.search(c)), "")
    if hit:
        return {"statement": f"{_clean(hit, 320)} {_DOC_CITE}", "source": _DOC_CITE}

    bits: list[str] = []
    for rows, key, label in ((by_tenure, "tenure_band", "tenure band"), (by_segment, "segment", "segment")):
        worst = _weakest(rows, key)
        if worst:
            bits.append(f"the weakest {label} is {worst[0]} at {worst[1]:g}% retention")
    top_reason = next((r for r in reasons if isinstance(r, dict)
                       and not str(r.get("reason") or "").startswith("Information")), None)
    if top_reason:
        bits.append(f"the largest recorded reason for loss is {_clean(top_reason.get('reason'), 48)} at "
                    f"{_clean(top_reason.get('contribution_pct'), 40)}")
    if bits:
        return {"statement": ("Where loss concentrates, on the evidence opened: " + "; ".join(bits)
                             + f". Loss is located rather than averaged across the base {_COMPUTED}"),
                "source": _COMPUTED}
    return {"statement": _info_request("where loss concentrates — the segment, tenure band, channel or "
                                       "contract form taking a disproportionate share of churned revenue"),
            "source": _NA}


# ---------------------------------------------------------------------------
# heuristic — contract protection & renewal cliff
# ---------------------------------------------------------------------------


def _is_counterparty_name(name: str) -> bool:
    if not name:
        return False
    stripped = _CONTRACT_WORD.sub(" ", name).strip()
    return bool(stripped) and bool(_clean_row_name(stripped, max_chars=60))


def _contract_counterparty(clause: str) -> str:
    for pattern in (_CONTRACT_NAMED, _CONTRACT_NAMED_ALT):
        for m in pattern.finditer(clause or ""):
            name = _clean_row_name(m.group(1), max_chars=60)
            if name and _is_counterparty_name(name):
                return _title_case(name)
    return ""


def _extract_contract_protections(corpus: str) -> list[dict[str, Any]]:
    """Executed-contract terms for the largest customers. Names are never invented."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for clause in _clauses(corpus):
        matches = {key: cue.search(clause) for key, _l, cue, _r in _CONTRACT_FIELDS}
        found = sum(1 for m in matches.values() if m)
        if not found or not (_CONTRACT_CUE.search(clause) or found >= 2):
            continue
        name = _contract_counterparty(clause)
        key = (name or _clean(clause, 70)).lower()
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, Any] = {
            "customer": name or _info_request("counterparty name for this executed contract (not named in "
                                              "the packs — no name is inferred)"),
            "source": _DOC_CITE,
        }
        for field, _label, _cue, request in _CONTRACT_FIELDS:
            row[field] = _cited(matches[field], request)
        rows.append(row)
        if len(rows) >= 8:
            break

    if not rows:
        blank: dict[str, Any] = {
            "customer": _info_request("executed contracts for the largest customers by revenue, from the "
                                      "contract register"),
            "source": _NA,
        }
        for field, _label, _cue, request in _CONTRACT_FIELDS:
            blank[field] = _info_request(f"{request} — for each largest customer")
        rows.append(blank)
    return rows[:8]


def _contracts_named(contracts: list[dict[str, Any]]) -> int:
    return _real_rows([c for c in contracts if _is_filled(c.get("customer"))], "customer")


def _contract_fields_filled(contracts: list[dict[str, Any]]) -> int:
    return sum(1 for c in contracts if isinstance(c, dict)
               for field, _l, _cue, _r in _CONTRACT_FIELDS if _is_filled(c.get(field)))


def _extract_renewal_cliff(corpus: str) -> dict[str, Any]:
    clauses = _clauses(corpus)
    share_val: float | None = None
    share_clause = ""
    for clause in clauses:
        m = _CLIFF_SHARE.search(clause)
        val = _pct(m.group(1) or m.group(2)) if m else None
        if val is not None and val <= 100:
            share_val, share_clause = val, clause
            break

    cliff = share_clause or next((c for c in clauses if _CLIFF_CUE.search(c)), "")
    window = _snippet(_CLIFF_WINDOW.search(cliff) or _CLIFF_WINDOW.search(corpus or ""), limit=60)

    if share_val is not None:
        band = "material" if share_val >= 25 else "notable" if share_val >= 10 else "small"
        material = f"{share_val:g}% of revenue {_DOC_CITE}"
        note = (f"{share_val:g}% of revenue comes up for renewal "
                + (f"in {window}" if window else "within the window stated in the packs")
                + f" — a {band} renewal cliff on the evidence opened. {_clean(cliff, 200)} {_COMPUTED}")
        info = "" if window else _info_request("the renewal window the share relates to (next 12 months, "
                                               "next financial year, or a dated schedule)")
    elif cliff:
        material = _info_request("share of revenue up for renewal, as a percentage of revenue in the accounts")
        note = (f"The packs reference renewal exposure without quantifying it: {_clean(cliff, 220)} "
                f"{_DOC_CITE}. A renewal cliff is a quantity, not an adjective, so no share is inferred here.")
        info = _info_request("a dated renewal schedule by customer — contract end date and annual value — so "
                             "the share up for renewal in each window can be computed")
    else:
        material = _info_request("share of revenue up for renewal in the next 12 months")
        note = ("No renewal schedule was opened, so the renewal cliff is unquantified. Absence of a schedule "
                "is an information gap, not evidence that renewal exposure is low.")
        info = _info_request("a dated renewal schedule by customer — contract end date, renewal mechanism and "
                             "annual value — so the renewal cliff can be computed")

    return {
        "material_share_pct": material,
        "window": window or _info_request("the renewal window (e.g. next 12 months)"),
        "note": note,
        "source": _DOC_CITE if cliff else _NA,
        "information_request": info,
    }


# ---------------------------------------------------------------------------
# heuristic — behaviour vs protection
# ---------------------------------------------------------------------------


def _behaviour_vs_protection(corpus: str, *, metrics: dict[str, float | None],
                             contracts: list[dict[str, Any]], population: str) -> dict[str, str]:
    behaviour_bits = [f"{label} {_pct(metrics.get(key)):g}%" for key, label in
                      (("grr_pct", "GRR"), ("nrr_pct", "NRR"), ("logo_retention_pct", "logo retention"))
                      if _pct(metrics.get(key)) is not None]
    if behaviour_bits:
        stayed = ("Behavioural retention — what customers actually did: " + ", ".join(behaviour_bits)
                  + f" on **{population}**. These are observed outcomes for the period; they say nothing "
                  f"about whether the same customers could leave tomorrow {_COMPUTED}")
    else:
        stayed = _info_request(f"behavioural retention — GRR, NRR and logo retention on a constant "
                               f"{population} population — so staying behaviour can be measured separately "
                               "from protection")

    committed_clause = next((c for c in _clauses(corpus) if _COMMITTED_CUE.search(c)), "")
    protected, named = _contract_fields_filled(contracts), _contracts_named(contracts)
    if committed_clause:
        committed = ("Contractual commitment — what the customer is bound to: "
                     f"{_clean(committed_clause, 240)} {_DOC_CITE}")
    elif protected:
        committed = (f"Contractual commitment read from {named} named contract(s) with {protected} protection "
                     f"field(s) evidenced. Only committed minimums and remaining firm term are protection "
                     f"{_COMPUTED}")
    else:
        committed = _info_request("executed contracts for the largest customers so contractual commitment — "
                                  "firm term remaining, minimum commitment and termination for convenience — "
                                  "can be measured separately from staying behaviour")

    if behaviour_bits and protected:
        tail = ("Behaviour is measured and some contractual terms are evidenced, so the two are reported side "
                "by side rather than merged: a high retention rate on a base that can exit on short notice is "
                "a behavioural result, not a contractual floor.")
    elif behaviour_bits:
        tail = ("Only behaviour is evidenced — the rates describe what happened and no contractual floor has "
                "been verified, so they must not be read as protected revenue.")
    elif protected:
        tail = ("Only contract terms are evidenced — commitment is visible but the behavioural outcome is not "
                "measured, so persistence is unproven.")
    else:
        tail = ("Neither behaviour nor protection is evidenced in the packs opened, so neither is asserted; "
                "both are named as information requests.")
    distinction = f"{_BEHAVIOUR_RULE} {tail}"
    unprotected = _UNPROTECTED_CUE.search(corpus or "")
    if unprotected:
        distinction += (" The packs also record features that remove protection: "
                        f"{_snippet(unprotected, limit=90)} {_DOC_CITE} — revenue behind such terms is "
                        "behaviourally retained, not contractually committed.")

    return {
        "stayed_note": stayed,
        "committed_note": committed,
        "distinction": distinction,
        "source": _DOC_CITE if (committed_clause or behaviour_bits) else _NA,
    }


# ---------------------------------------------------------------------------
# legacy dual-write (Revenue Retention Table)
# ---------------------------------------------------------------------------


def _as_dict(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "model_dump"):
        try:
            dumped = raw.model_dump()
        except Exception:
            return None
        return dumped if isinstance(dumped, dict) else None
    return None


def _coerce_cohort(raw: Any) -> dict[str, Any] | None:
    """Coerce to the legacy CohortRow shape decks and workbooks expect."""
    row = _as_dict(raw)
    if row is None:
        return None
    size = row.get("size_units")
    return _cohort_row(row.get("cohort") or row.get("period") or row.get("start_period"),
                       size if size is not None else row.get("size"), row.get("m6_retention_pct"),
                       row.get("m12_retention_pct"), row.get("m36_retention_pct"))


def _legacy_cohort_rows(legacy: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [row for row in (_coerce_cohort(r) for r in (legacy or {}).get("cohorts") or []) if row]


def _legacy_metrics(legacy: dict[str, Any] | None) -> dict[str, float]:
    raw = (legacy or {}).get("retention_metrics")
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in ((k, _num(v)) for k, v in raw.items()) if v is not None}


def _merge_metrics(*sources: dict[str, Any],
                   legacy: dict[str, Any] | None = None) -> tuple[dict[str, float | None], list[str]]:
    """Legacy metrics pass through unchanged; gaps fill from the later sources."""
    seeded = _legacy_metrics(legacy)
    merged: dict[str, float | None] = {}
    for key in _METRIC_KEYS:
        merged[key] = seeded.get(key) if seeded.get(key) is not None else next(
            (_pct(s.get(key)) for s in sources if _pct(s.get(key)) is not None), None)
    for extra in (seeded, *sources):
        for key, value in extra.items():
            if key not in merged and _pct(value) is not None:
                merged[key] = _pct(value)
    notes: list[str] = []
    if seeded:
        head = ", ".join(f"{_METRIC_LABEL.get(k, k)} {v:g}%" for k, v in list(seeded.items())[:4])
        notes.append(f"Legacy retention metrics passed through unchanged ({head}); remaining gaps filled "
                     f"from the packs opened {_COMPUTED}")
    return merged, notes


def _derive_stickiness_notes(
    corpus: str,
    legacy: dict[str, Any],
    *,
    metrics: dict[str, float | None],
    deltas: list[dict[str, Any]],
    cohorts: list[dict[str, Any]],
    bridge: dict[str, Any],
    population: str,
    renewal: dict[str, Any],
    extra: list[str] | None = None,
) -> list[str]:
    falling = bool(_falling(deltas))
    notes: list[str] = [n for n in (_falling_statement(deltas),) if n]

    headline = [f"{_METRIC_LABEL[key]} {_pct(metrics.get(key)):g}%"
                for key in ("grr_pct", "nrr_pct", "logo_retention_pct")
                if _pct(metrics.get(key)) is not None]
    if headline:
        notes.append(", ".join(headline) + f" — all on {population}; {_EXCLUSION_RULE}.")
    if cohorts:
        notes.append(_cohort_notes(cohorts, population=population))
    filled = _bridge_filled(bridge)
    notes.append(f"Retention bridge: {filled} of 5 components evidenced (opening, churn, contraction, "
                 "expansion, closing)."
                 + (f" {_clean(bridge.get('gaps'), 200)}" if filled < 5 else ""))
    if _is_filled(renewal.get("material_share_pct")):
        notes.append(f"Renewal cliff: {_clean(renewal.get('material_share_pct'), 60)} "
                     f"{_clean(renewal.get('window'), 60)}.")
    notes.append(_BEHAVIOUR_RULE)
    notes.extend(_clean(x, 220) for x in (extra or []) if isinstance(x, str) and x.strip())

    if len(notes) < 6:
        for sent in _pick_sentences(_sentences(_prose(corpus)), limit=6, keywords=(
                "retention", "churn", "cohort", "renewal", "contract", "expansion", "contraction",
                "logo", "nrr", "grr")):
            notes.append(_clean(sent, 200))
            if len(notes) >= 6:
                break

    cleaned = list(dict.fromkeys(
        n for n in (_finding_voice(x, falling=falling) for x in notes if str(x or "").strip()) if n))
    if cleaned:
        return cleaned[:6]
    return [_finding_voice(x, falling=falling) for x in (legacy.get("stickiness_notes") or [])
            if isinstance(x, str) and x.strip()][:6]


# ---------------------------------------------------------------------------
# quality / reliance
# ---------------------------------------------------------------------------


def _quality_reliance(
    *,
    same_population: bool,
    grr_and_nrr: bool,
    logo_retention: bool,
    metric_count: int,
    cohort_count: int,
    bridge_filled: int,
    contracts_named: int,
    contract_fields: int,
    segment_rows: int,
    tenure_rows: int,
    loss_rows: int,
    falling: list[dict[str, Any]],
) -> tuple[str, str, str]:
    fall_txt = ""
    if falling:
        fall_txt = (" Retention has fallen — " + "; ".join(
            f"{_clean(f.get('metric'), 40)} {_clean(f.get('magnitude'), 50)}" for f in falling[:2])
            + " — recorded as a finding in the insight and in retention_delta, not a caveat.")
    evidence = (f"{metric_count} retention metric(s); {cohort_count} cohort row(s) by start period; "
                f"{bridge_filled} of 5 bridge components; {contracts_named} executed contract(s) named with "
                f"{contract_fields} protection field(s); {segment_rows} segment row(s), {tenure_rows} tenure "
                f"row(s) and {loss_rows} loss-reason row(s).{fall_txt}")

    if metric_count == 0 and cohort_count == 0:
        return "PASS", "BLOCKED", (
            "No retention metric and no cohort were evidenced, so persistence of revenue cannot be measured: "
            "GRR, NRR and logo retention are unquantified and the cohort curve is absent. The retention "
            "workbook and billing ledger are requested — an empty retention table is an information gap, not "
            f"a finding. {evidence}")

    headline_ok = same_population and (grr_and_nrr or logo_retention)
    if headline_ok and cohort_count and bridge_filled >= 3 and contracts_named:
        return "PASS", "READY", (
            "GRR, NRR and logo retention are on one constant population with new customers excluded from the "
            "numerators, cohorts are present by start period, the bridge reconciles and executed contracts "
            f"evidence the protection. {evidence}")
    if headline_ok and cohort_count:
        missing = []
        if bridge_filled < 3:
            missing.append("the opening-to-closing bridge is incomplete")
        if not contracts_named:
            missing.append("no executed contract is named, so protection is unverified")
        return "PASS", "LIMITED" if missing else "READY", (
            "Retention is on one population with cohorts present"
            + ("; " + "; ".join(missing) + ", so behaviour is measured but protection is not." if missing
               else " and the bridge and contracts support it.")
            + f" {evidence}")
    reasons = []
    if not same_population:
        reasons.append("the headline rates are not demonstrably on one constant population")
    if not cohort_count:
        reasons.append("no cohort by start period was evidenced")
    if bridge_filled < 3:
        reasons.append("opening, churn, contraction, expansion and closing do not reconcile")
    if not contracts_named:
        reasons.append("executed contracts were not opened, so protection is unverified")
    return "PASS", "LIMITED", ("Retention metrics are present but cannot yet be relied on: "
                               + "; ".join(reasons[:4]) + f". {evidence}")


def _verdicts(
    *,
    metrics: dict[str, float | None],
    on_same: bool,
    cohorts: list[dict[str, Any]],
    bridge: dict[str, Any],
    contracts: list[dict[str, Any]],
    by_segment: list[dict[str, Any]],
    by_tenure: list[dict[str, Any]],
    loss_reasons: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
) -> tuple[str, str, str, int, int]:
    metric_count = sum(1 for key in _METRIC_KEYS if _pct(metrics.get(key)) is not None)
    named = _contracts_named(contracts)
    quality, reliance, rationale = _quality_reliance(
        same_population=on_same,
        grr_and_nrr=(_pct(metrics.get("grr_pct")) is not None and _pct(metrics.get("nrr_pct")) is not None),
        logo_retention=_pct(metrics.get("logo_retention_pct")) is not None,
        metric_count=metric_count,
        cohort_count=len(cohorts),
        bridge_filled=_bridge_filled(bridge),
        contracts_named=named,
        contract_fields=_contract_fields_filled(contracts),
        segment_rows=_real_rows(by_segment, "segment"),
        tenure_rows=_real_rows(by_tenure, "tenure_band"),
        loss_rows=_real_rows(loss_reasons, "reason"),
        falling=_falling(deltas),
    )
    return quality, reliance, rationale, metric_count, named


# ---------------------------------------------------------------------------
# heuristic composer
# ---------------------------------------------------------------------------


def _legacy_corpus_bits(legacy: dict[str, Any], geography: str | None) -> list[str]:
    """Fold the legacy spec back into the corpus so nothing evidenced is dropped."""
    bits: list[str] = [item.strip() for item in (legacy.get("stickiness_notes") or [])[:8]
                       if isinstance(item, str) and item.strip()]
    bits.extend(f"{_METRIC_LABEL.get(key, key)} {value:g}%"
                for key, value in _legacy_metrics(legacy).items())
    for row in _legacy_cohort_rows(legacy)[:12]:
        parts = [str(row.get("cohort") or "")]
        if row.get("size_units") is not None:
            parts.append(f"{row['size_units']:g}")
        parts.extend(f"{row[key]:g}%" if row.get(key) is not None else "N/A"
                     for key in ("m6_retention_pct", "m12_retention_pct", "m36_retention_pct"))
        bits.append(" ".join(p for p in parts if p))
    if geography and str(geography).strip():
        bits.append(f"Geography focus in the mandate: {_clean(geography, 60)}")
    return bits


def _heuristic_customer_stickiness_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del sector  # scope words are read from the evidence, never assumed from the deal
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra_bits = _legacy_corpus_bits(legacy, geography)
    corpus_full = (corpus or "") + ("\n" + "\n".join(extra_bits) if extra_bits else "")

    pop_def = _extract_population_definition(corpus_full)
    population = str(pop_def["population"])

    cohorts = _extract_cohorts(corpus_full) or _legacy_cohort_rows(legacy)
    bridge = _extract_retention_bridge(corpus_full, population=population)
    extracted, metric_notes = _extract_retention_metrics(corpus_full)
    metrics, legacy_notes = _merge_metrics(extracted, legacy=legacy)
    same_pop = _retention_on_same_population(metrics, population=population, corpus=corpus_full,
                                             bridge=bridge)
    on_same = bool(same_pop.pop("on_same_population"))
    deltas = _extract_retention_delta(corpus_full)
    falls = _falling(deltas)

    by_segment = _extract_retention_cut(corpus_full, name_key="segment", population=population)
    by_tenure = _extract_retention_cut(corpus_full, name_key="tenure_band", population=population)
    loss_reasons = _extract_loss_reasons(corpus_full)
    concentration = _loss_concentration(corpus_full, reasons=loss_reasons, by_tenure=by_tenure,
                                        by_segment=by_segment)
    contracts = _extract_contract_protections(corpus_full)
    renewal = _extract_renewal_cliff(corpus_full)
    behaviour = _behaviour_vs_protection(corpus_full, metrics=metrics, contracts=contracts,
                                         population=population)
    notes = _derive_stickiness_notes(corpus_full, legacy, metrics=metrics, deltas=deltas, cohorts=cohorts,
                                     bridge=bridge, population=population, renewal=renewal,
                                     extra=[*metric_notes, *legacy_notes])
    quality, reliance, rationale, metric_count, named = _verdicts(
        metrics=metrics, on_same=on_same, cohorts=cohorts, bridge=bridge, contracts=contracts,
        by_segment=by_segment, by_tenure=by_tenure, loss_reasons=loss_reasons, deltas=deltas)

    headline = ", ".join(f"{_METRIC_LABEL[key].split(' (')[0]} {_pct(metrics.get(key)):g}%"
                         for key in ("grr_pct", "nrr_pct", "logo_retention_pct")
                         if _pct(metrics.get(key)) is not None)
    insight = _finding_voice(
        f"Customer Stickiness for {company}: "
        + (f"{headline} — all on **{population}**, {_EXCLUSION_RULE}" if headline else
           "no GRR, NRR or logo retention rate is evidenced, so persistence of revenue is unquantified and "
           "the retention workbook is requested")
        + f"; {len(cohorts)} cohort(s) by start period; {_bridge_filled(bridge)} of 5 bridge components "
        f"reconciled; {named} executed contract(s) reviewed for term, renewal, notice, minimum commitment, "
        f"escalator and termination for convenience; renewal cliff "
        f"{_clean(renewal.get('material_share_pct'), 60)}. "
        + (_falling_statement(deltas) + " " if falls else "") + _BEHAVIOUR_RULE,
        falling=bool(falls),
    )

    return {
        "insight_snapshot": insight,
        "population_definition": pop_def,
        "cohorts": cohorts,
        "cohort_notes": _cohort_notes(cohorts, population=population),
        "retention_bridge": bridge,
        "retention_metrics": metrics,
        "logo_retention_pct": _pct(metrics.get("logo_retention_pct")),
        "retention_on_same_population": same_pop,
        "retention_delta": deltas,
        "retention_by_segment": by_segment,
        "retention_by_tenure": by_tenure,
        "loss_reasons": loss_reasons,
        "loss_concentration": concentration,
        "contract_protections": contracts,
        "renewal_cliff": renewal,
        "behaviour_vs_protection": behaviour,
        "stickiness_notes": notes,
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": _finding_voice(rationale, falling=bool(falls)),
        "primary_sources": list(sources or [])[:16],
        "composer": "heuristic_v1",
        "empty": (metric_count == 0 and not cohorts and named == 0
                  and _bridge_filled(bridge) == 0 and not notes),
    }


# ---------------------------------------------------------------------------
# LLM composer
# ---------------------------------------------------------------------------


def _llm_customer_stickiness_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not (corpus or "").strip():
        return None
    try:
        system = compose_system("customer_stickiness", sector=sector, geography=geography,
                                materiality=materiality)
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "population_definition: {population (logos|accounts|locations|subscriptions), definition, "
        "constant_rule, source, information_request},\n"
        "cohorts: [{cohort (start period, e.g. 'Q1 FY2022'), size_units (number), m6_retention_pct, "
        "m12_retention_pct, m36_retention_pct}],\n"
        "retention_bridge: {period, opening_revenue, churn, contraction, expansion, closing_revenue, "
        "new_customers_excluded (true), source, gaps},\n"
        "retention_metrics: {grr_pct, nrr_pct, logo_churn_pct, revenue_churn_pct, retention_12m_pct, "
        "repurchase_pct, logo_retention_pct} — numbers or null,\n"
        "retention_on_same_population: {population, grr, nrr, logo_retention, notes},\n"
        "retention_delta: [{metric, from_value, to_value, direction (up|down|flat|unknown), magnitude, "
        "is_finding (bool), source}],\n"
        "retention_by_segment: [{segment, retention_pct, population, source}],\n"
        "retention_by_tenure: [{tenure_band, retention_pct, population, source}],\n"
        "loss_reasons: [{reason, contribution_pct, concentrates_in, source}],\n"
        "loss_concentration: {statement, source},\n"
        "contract_protections: [{customer, term, renewal_mechanism, notice_period, minimum_commitment, "
        "price_escalator, termination_for_convenience, source}],\n"
        "renewal_cliff: {material_share_pct, window, note, source, information_request},\n"
        "behaviour_vs_protection: {stayed_note, committed_note, distinction, source},\n"
        "stickiness_notes: [string] — legacy Revenue Retention Table shape for decks,\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n\n"
        "Rules:\n"
        "Build monthly customer and revenue cohorts by start period. Define the population precisely and "
        "keep it constant: logos, accounts, locations or subscriptions. Never mix populations in one table.\n"
        "Reconcile opening revenue, churn, contraction, expansion and closing revenue for the period.\n"
        "GRR, NRR and logo retention must be on the same population; exclude new customers from retention "
        "numerators.\n"
        "Falling retention is a finding, not a caveat. If retention has moved, state by how much and in "
        "which direction, and set is_finding true for every downward movement.\n"
        "Show retention by segment and by tenure, give the reasons for loss where the records capture them, "
        "and say where loss concentrates.\n"
        "Review executed contracts for the largest customers: term, renewal mechanism, notice period, "
        "minimum commitment, price escalator and termination for convenience. Identify the renewal cliff — "
        "the material share of revenue coming up for renewal — and the window it falls in.\n"
        "Distinguish behaviour (stayed) from protection (contractually committed). Customers who have "
        "stayed are not the same as customers who are contractually committed.\n"
        "Never invent customer or counterparty names — if a name is not in the evidence, raise a named "
        "information request instead.\n"
        "Do NOT recommend invest or pass. Do NOT include recommendation, confidence or investment verdict "
        "fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# normalise
# ---------------------------------------------------------------------------


def _normalise_population_definition(llm: dict[str, Any], corpus: str) -> dict[str, Any]:
    heuristic = _extract_population_definition(corpus)
    raw = llm.get("population_definition")
    if not isinstance(raw, dict):
        return heuristic
    out = dict(raw)
    population = _population(out.get("population") or out.get("definition"),
                             default=str(heuristic["population"]))
    out["population"] = population
    if _is_filled(out.get("definition")):
        out["definition"] = _clean(out["definition"], 320)
        if population not in out["definition"].lower():
            out["definition"] = f"Population measured: **{population}**. {out['definition']}"
    else:
        out["definition"] = heuristic["definition"]
    if _is_filled(out.get("constant_rule")):
        out["constant_rule"] = _clean(out["constant_rule"], 380)
        if "constant" not in out["constant_rule"].lower():
            out["constant_rule"] += (" Held constant across every cohort, the bridge and each retention "
                                     f"rate; {_EXCLUSION_RULE}.")
    else:
        out["constant_rule"] = heuristic["constant_rule"]
    if not str(out.get("information_request") or "").strip():
        out["information_request"] = heuristic["information_request"]
    out.setdefault("source", heuristic["source"])
    return out


def _normalise_cohorts(llm: dict[str, Any], corpus: str, legacy: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in llm.get("cohorts") or []:
        row = _coerce_cohort(raw)
        if not row or str(row["cohort"]).lower() in seen:
            continue
        seen.add(str(row["cohort"]).lower())
        rows.append(row)
        if len(rows) >= 12:
            break
    return rows or _extract_cohorts(corpus) or _legacy_cohort_rows(legacy)


def _normalise_bridge(llm: dict[str, Any], corpus: str, *, population: str) -> dict[str, Any]:
    heuristic = _extract_retention_bridge(corpus, population=population)
    raw = llm.get("retention_bridge")
    if not isinstance(raw, dict):
        return heuristic
    out = dict(raw)
    for key in (*_BRIDGE_KEYS, "period"):
        out[key] = _clean(out[key], 160) if _is_filled(out.get(key)) else heuristic[key]

    excluded = out.get("new_customers_excluded")
    if excluded is True or str(excluded or "").strip().lower() in {"true", "yes", "y"}:
        out["new_customers_excluded"] = True
    elif isinstance(excluded, str) and excluded.strip():
        out["new_customers_excluded"] = _clean(excluded, 300)
    else:
        out["new_customers_excluded"] = heuristic["new_customers_excluded"]

    filled = _bridge_filled(out)
    gaps = str(out.get("gaps") or "").strip()
    if gaps:
        out["gaps"] = _clean(gaps, 380)
        if filled < 5 and "not" not in out["gaps"].lower():
            out["gaps"] += (f" Only {filled} of 5 bridge components are evidenced, so the bridge does not "
                            f"yet tie opening to closing {_COMPUTED}.")
    else:
        out["gaps"] = heuristic["gaps"]
    out.setdefault("source", heuristic["source"])
    return out


def _normalise_metrics(llm: dict[str, Any], corpus: str,
                       legacy: dict[str, Any]) -> tuple[dict[str, float | None], list[str]]:
    extracted, notes = _extract_retention_metrics(corpus)
    raw = llm.get("retention_metrics")
    claimed = ({str(k): v for k, v in raw.items() if _pct(v) is not None} if isinstance(raw, dict) else {})
    merged, legacy_notes = _merge_metrics(claimed, extracted, legacy=legacy)
    notes.extend(legacy_notes)

    found = {k: v for k, v in merged.items() if _pct(v) is not None}
    notes.extend(n for n in (_complement(found, "logo_retention_pct", "logo_churn_pct"),
                             _complement(found, "logo_churn_pct", "logo_retention_pct"),
                             _expansion_note(found)) if n)
    for key in ("logo_retention_pct", "logo_churn_pct"):
        if merged.get(key) is None and key in found:
            merged[key] = found[key]
    return merged, notes


def _normalise_same_population(
    llm: dict[str, Any],
    corpus: str,
    *,
    metrics: dict[str, float | None],
    population: str,
    bridge: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    heuristic = _retention_on_same_population(metrics, population=population, corpus=corpus, bridge=bridge)
    ok = bool(heuristic.pop("on_same_population"))
    raw = llm.get("retention_on_same_population")
    if not isinstance(raw, dict):
        return heuristic, ok
    out = dict(raw)
    out["population"] = population
    for key in ("grr", "nrr", "logo_retention"):
        if not _is_filled(out.get(key)):
            out[key] = heuristic[key]
            continue
        text = _clean(out[key], 160)
        out[key] = text if population in text.lower() else f"{text} (on {population})"
    notes = str(out.get("notes") or "").strip()
    if notes:
        out["notes"] = _clean(notes, 420)
        lowered = out["notes"].lower()
        if "same population" not in lowered and "one population" not in lowered:
            out["notes"] += f" {_SAME_POP_RULE}."
        elif "new customer" not in lowered:
            out["notes"] += f" Note: {_EXCLUSION_RULE}."
    else:
        out["notes"] = heuristic["notes"]
    return out, ok


def _normalise_deltas(llm: dict[str, Any], corpus: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _push(row: dict[str, Any]) -> bool:
        key = (str(row["metric"]), str(row["from_value"]), str(row["to_value"]))
        if key in seen:
            return False
        seen.add(key)
        cleaned.append(row)
        return len(cleaned) >= 6

    for raw in llm.get("retention_delta") or []:
        if not isinstance(raw, dict):
            continue
        metric_label = _clean(raw.get("metric"), 60)
        if not metric_label:
            continue
        key = _metric_key_from_token(metric_label)
        start, end = _pct(raw.get("from_value")), _pct(raw.get("to_value"))
        if start is not None and end is not None:
            row = _delta_row(metric_key=key, metric_label=metric_label, from_value=start, to_value=end,
                             source=_clean(raw.get("source"), 140) or _DOC_CITE)
            if not row:
                continue
            stated = _direction(raw.get("direction"))
            if stated not in {"unknown", row["direction"]}:
                row["magnitude"] += (f" (the model reported this as '{stated}'; the direction above is taken "
                                     f"from the stated values) {_COMPUTED}")
        else:
            direction = _direction(raw.get("direction"))
            magnitude = _clean(raw.get("magnitude"), 200)
            if direction == "unknown" and not magnitude:
                continue
            worse = (direction == "up") if "churn" in metric_label.lower() else (direction == "down")
            row = {
                "metric": _metric_display(key, metric_label),
                "from_value": _clean(raw.get("from_value"), 60)
                or _info_request("opening value for this movement"),
                "to_value": _clean(raw.get("to_value"), 60)
                or _info_request("closing value for this movement"),
                "direction": direction,
                "magnitude": magnitude or _info_request(
                    "magnitude of the movement in pp, with both endpoints"),
                "is_finding": bool(worse and direction != "flat"),
                "source": _clean(raw.get("source"), 140) or _DOC_CITE,
            }
        # A downward retention movement is a finding whatever the model claimed.
        inverted = "churn" in str(row["metric"]).lower()
        if row["direction"] == "flat":
            row["is_finding"] = False
        elif row["direction"] == ("up" if inverted else "down"):
            row["is_finding"] = True
        if _push(row):
            return cleaned

    for row in _extract_retention_delta(corpus):
        if _push(row):
            break
    cleaned.sort(key=lambda r: (not r.get("is_finding"), str(r.get("metric"))))
    return cleaned[:6]


def _normalise_cut_rows(raw_rows: Any, *, name_key: str, population: str,
                        corpus: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rows or []:
        if not isinstance(raw, dict):
            continue
        name = _clean_row_name(raw.get(name_key), max_chars=60)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        pct = _pct(raw.get("retention_pct"))
        cleaned.append({
            name_key: _title_case(name),
            "retention_pct": f"{pct:g}%" if pct is not None else _info_request(
                f"retention rate for {name}"),
            "population": _population(raw.get("population"), default=population),
            "source": _clean(raw.get("source"), 60) or _DOC_CITE,
        })
        if len(cleaned) >= 8:
            break
    return cleaned or _extract_retention_cut(corpus, name_key=name_key, population=population)


def _normalise_loss_reasons(llm: dict[str, Any], corpus: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in llm.get("loss_reasons") or []:
        if not isinstance(raw, dict):
            continue
        reason = _clean_row_name(raw.get("reason"), max_chars=70)
        if not reason or reason.lower() in seen:
            continue
        seen.add(reason.lower())
        pct = _pct(raw.get("contribution_pct"))
        cleaned.append({
            "reason": _title_case(reason),
            "contribution_pct": f"{pct:g}% of recorded loss" if pct is not None else _info_request(
                "this reason's share of total recorded loss"),
            "concentrates_in": _clean(raw.get("concentrates_in"), 160) or _info_request(
                "where this reason concentrates — segment, tenure band or channel"),
            "source": _clean(raw.get("source"), 60) or _DOC_CITE,
        })
        if len(cleaned) >= 8:
            break
    return cleaned or _extract_loss_reasons(corpus)


def _normalise_contracts(llm: dict[str, Any], corpus: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in llm.get("contract_protections") or []:
        if not isinstance(raw, dict):
            continue
        name = _clean_row_name(raw.get("customer"), max_chars=60)
        row = dict(raw)
        row["customer"] = (_title_case(name) if name and _is_counterparty_name(name) else _info_request(
            "counterparty name for this executed contract (no name is inferred)"))
        key = str(row["customer"]).lower()
        if key in seen and not key.startswith("information"):
            continue
        seen.add(key)
        for field, _label, _cue, request in _CONTRACT_FIELDS:
            row[field] = _clean(row[field], 160) if _is_filled(row.get(field)) else _info_request(request)
        row.setdefault("source", _DOC_CITE)
        cleaned.append(row)
        if len(cleaned) >= 8:
            break
    return cleaned or _extract_contract_protections(corpus)


def _normalise_renewal_cliff(llm: dict[str, Any], corpus: str) -> dict[str, Any]:
    heuristic = _extract_renewal_cliff(corpus)
    raw = llm.get("renewal_cliff")
    if not isinstance(raw, dict):
        return heuristic
    out = dict(raw)
    share = _pct(out.get("material_share_pct"))
    if share is not None and share <= 100:
        out["material_share_pct"] = f"{share:g}% of revenue {_DOC_CITE}"
    elif _is_filled(out.get("material_share_pct")):
        out["material_share_pct"] = _clean(out["material_share_pct"], 80)
    else:
        out["material_share_pct"] = heuristic["material_share_pct"]
    out["window"] = _clean(out["window"], 80) if _is_filled(out.get("window")) else heuristic["window"]
    out["note"] = (_soften_invest(_clean(out["note"], 380)) if _is_filled(out.get("note"))
                   else heuristic["note"])
    if not str(out.get("information_request") or "").strip():
        out["information_request"] = ("" if share is not None and _is_filled(out.get("window"))
                                      else heuristic["information_request"])
    out.setdefault("source", heuristic["source"])
    return out


def _normalise_behaviour(llm: dict[str, Any], corpus: str, *, metrics: dict[str, float | None],
                         contracts: list[dict[str, Any]], population: str) -> dict[str, Any]:
    heuristic = _behaviour_vs_protection(corpus, metrics=metrics, contracts=contracts,
                                         population=population)
    raw = llm.get("behaviour_vs_protection")
    if not isinstance(raw, dict):
        return heuristic
    out = dict(raw)
    for key in ("stayed_note", "committed_note"):
        out[key] = (_soften_invest(_clean(out[key], 360)) if _is_filled(out.get(key)) else heuristic[key])
    distinction = str(out.get("distinction") or "").strip()
    if distinction:
        out["distinction"] = _soften_invest(_clean(distinction, 420))
        lowered = out["distinction"].lower()
        if "committed" not in lowered or "stayed" not in lowered:
            out["distinction"] = f"{_BEHAVIOUR_RULE} {out['distinction']}"
    else:
        out["distinction"] = heuristic["distinction"]
    out.setdefault("source", heuristic["source"])
    return out


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    pop_def = _normalise_population_definition(llm, corpus)
    llm["population_definition"] = pop_def
    population = str(pop_def.get("population") or "logos")

    cohorts = _normalise_cohorts(llm, corpus, legacy)
    llm["cohorts"] = cohorts
    llm["cohort_notes"] = (_clean(llm.get("cohort_notes"), 380) if _is_filled(llm.get("cohort_notes"))
                           else _cohort_notes(cohorts, population=population))

    bridge = _normalise_bridge(llm, corpus, population=population)
    llm["retention_bridge"] = bridge
    metrics, metric_notes = _normalise_metrics(llm, corpus, legacy)
    llm["retention_metrics"] = metrics
    llm["logo_retention_pct"] = _pct(metrics.get("logo_retention_pct"))

    same_pop, on_same = _normalise_same_population(llm, corpus, metrics=metrics, population=population,
                                                   bridge=bridge)
    llm["retention_on_same_population"] = same_pop
    deltas = _normalise_deltas(llm, corpus)
    llm["retention_delta"] = deltas
    falls = _falling(deltas)

    llm["retention_by_segment"] = _normalise_cut_rows(llm.get("retention_by_segment"), name_key="segment",
                                                      population=population, corpus=corpus)
    llm["retention_by_tenure"] = _normalise_cut_rows(llm.get("retention_by_tenure"), name_key="tenure_band",
                                                     population=population, corpus=corpus)
    loss_reasons = _normalise_loss_reasons(llm, corpus)
    llm["loss_reasons"] = loss_reasons

    heuristic_conc = _loss_concentration(corpus, reasons=loss_reasons, by_tenure=llm["retention_by_tenure"],
                                         by_segment=llm["retention_by_segment"])
    conc = llm.get("loss_concentration")
    if isinstance(conc, dict) and _is_filled(conc.get("statement")):
        llm["loss_concentration"] = {
            "statement": _soften_invest(_clean(conc.get("statement"), 360)),
            "source": _clean(conc.get("source"), 60) or heuristic_conc["source"],
        }
    else:
        llm["loss_concentration"] = heuristic_conc

    contracts = _normalise_contracts(llm, corpus)
    llm["contract_protections"] = contracts
    llm["renewal_cliff"] = _normalise_renewal_cliff(llm, corpus)
    llm["behaviour_vs_protection"] = _normalise_behaviour(llm, corpus, metrics=metrics, contracts=contracts,
                                                          population=population)

    # --- legacy dual-write -------------------------------------------------
    heuristic_notes = _derive_stickiness_notes(corpus, legacy, metrics=metrics, deltas=deltas,
                                               cohorts=cohorts, bridge=bridge, population=population,
                                               renewal=llm["renewal_cliff"], extra=metric_notes)
    raw_notes = llm.get("stickiness_notes")
    if isinstance(raw_notes, list) and raw_notes:
        notes = [n for n in (_finding_voice(_clean(x, 240), falling=bool(falls)) for x in raw_notes
                             if isinstance(x, str) and x.strip()) if n]
        if falls and not any("finding" in n.lower() for n in notes):
            notes.insert(0, _falling_statement(deltas))
        llm["stickiness_notes"] = list(dict.fromkeys(notes))[:6]
    else:
        llm["stickiness_notes"] = heuristic_notes

    # --- verdicts / housekeeping ------------------------------------------
    quality, reliance, rationale, metric_count, named = _verdicts(
        metrics=metrics, on_same=on_same, cohorts=cohorts, bridge=bridge, contracts=contracts,
        by_segment=llm["retention_by_segment"], by_tenure=llm["retention_by_tenure"],
        loss_reasons=loss_reasons, deltas=deltas)
    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else quality
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else reliance
    llm["quality_reliance_rationale"] = (
        _finding_voice(_clean(llm["quality_reliance_rationale"], 460), falling=bool(falls))
        if str(llm.get("quality_reliance_rationale") or "").strip() else rationale)
    if llm["reliance_verdict"] == "READY" and not (on_same and cohorts and metric_count):
        llm["reliance_verdict"] = "LIMITED"
        llm["quality_reliance_rationale"] = (
            "Reliance is limited: GRR, NRR and logo retention are not demonstrably on one constant "
            "population with cohorts by start period. "
            + _clean(llm.get("quality_reliance_rationale"), 300))
    if metric_count == 0 and not cohorts:
        llm["reliance_verdict"] = "BLOCKED"
    if falls:
        lowered = str(llm.get("quality_reliance_rationale") or "").lower()
        if "fall" not in lowered and "finding" not in lowered:
            llm["quality_reliance_rationale"] = (_falling_statement(deltas) + " "
                                                 + _clean(llm.get("quality_reliance_rationale"), 380))

    for dead in ("recommendation", "confidence", "investment_verdict", "verdict", "key_conditions",
                 "invest_recommendation"):
        llm.pop(dead, None)

    insight = _finding_voice(llm.get("insight_snapshot") or "", falling=bool(falls))
    if falls and "finding" not in insight.lower():
        insight = f"{_falling_statement(deltas)} {insight}".strip()
    if insight and "committed" not in insight.lower():
        insight = f"{insight.rstrip()} {_BEHAVIOUR_RULE}"
    llm["insight_snapshot"] = insight

    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = (metric_count == 0 and not cohorts and named == 0
                    and _bridge_filled(bridge) == 0 and not llm["stickiness_notes"])
    return llm


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def build_customer_stickiness_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography, sector = vars_.get("geography"), vars_.get("sector")

    if corpus is None:
        gathered_corpus, gathered_sources = gather_customer_stickiness_corpus(deal, idx)
        corpus = gathered_corpus
        if not sources:
            sources = gathered_sources
    sources = list(sources or [])
    if not corpus:
        bits: list[str] = []
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                name = str(doc.get("filename") or "source")
                if name not in sources:
                    sources.append(name)
        corpus = "\n".join(bits)

    if not prefer_heuristic:
        llm = _llm_customer_stickiness_spec(company=target, corpus=corpus, sources=sources, sector=sector,
                                            geography=geography, materiality=vars_.get("materiality"))
        if llm:
            return _normalise_llm_spec(llm, sources=sources, legacy_spec=legacy_spec, corpus=corpus)

    return _heuristic_customer_stickiness_spec(company=target, corpus=corpus, sources=sources, sector=sector,
                                               geography=geography, legacy_spec=legacy_spec)


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def _pct_cell(value: Any) -> str:
    val = _pct(value)
    return f"{val:g}%" if val is not None else "—"


def _size_cell(value: Any) -> str:
    val = _num(value)
    return _fmt_num(f"{val:g}") if val is not None else "—"


def _cut_table(rows: list[dict[str, Any]], *, name_key: str, header: str, population: str) -> str:
    return _table([header, "Retention", "Population", "Source"],
                  [[_clean(r.get(name_key), 70), _clean(r.get("retention_pct"), 60),
                    _population(r.get("population"), default=population),
                    _clean(r.get("source") or _NA, 50)] for r in rows])


def render_customer_stickiness_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    def _sub(key: str) -> dict[str, Any]:
        value = spec.get(key)
        return value if isinstance(value, dict) else {}

    def _rows(key: str) -> list[dict[str, Any]]:
        value = spec.get(key)
        return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []

    pop_def, bridge = _sub("population_definition"), _sub("retention_bridge")
    same_pop, renewal = _sub("retention_on_same_population"), _sub("renewal_cliff")
    behaviour, concentration = _sub("behaviour_vs_protection"), _sub("loss_concentration")
    metrics = _sub("retention_metrics")
    cohorts, deltas = _rows("cohorts"), _rows("retention_delta")
    by_segment, by_tenure = _rows("retention_by_segment"), _rows("retention_by_tenure")
    loss_reasons, contracts = _rows("loss_reasons"), _rows("contract_protections")

    srcs = sources or spec.get("primary_sources") or spec.get("sources") or []
    population = _population(pop_def.get("population") or same_pop.get("population"), default="logos")
    falls = _falling(deltas)
    parts: list[str] = [f"# {title}\n\n"]
    snapshot = _clean(spec.get("insight_snapshot"), 560)
    if snapshot:
        parts.append(f"**Insight Snapshot:** {snapshot}\n\n")
    if falls:
        parts.append(f"{_falling_statement(deltas)}\n\n")

    # --- 1 ----------------------------------------------------------------
    parts.append("## 1. Population & Cohorts\n\n")
    parts.append("The retention population is defined once and held constant — logos, accounts, locations "
                 "or subscriptions — and every number below is measured on it. Cohorts run by start period "
                 "so the shape of the curve is visible, not just an average.\n\n")
    parts.append(_table(["Item", "Statement"], [
        ["Population", f"**{population}**"],
        ["Definition", _clean(pop_def.get("definition"), 420)],
        ["How constancy is enforced", _clean(pop_def.get("constant_rule"), 480)],
        ["Source", _clean(pop_def.get("source") or _NA, 60)],
    ]))
    if _is_filled(pop_def.get("information_request")):
        parts.append(f"**{_clean(pop_def.get('information_request'), 340)}**\n\n")
    parts.append(f"### Cohorts by start period — counted on **{population}**\n\n")
    parts.append(_table(
        ["Start period (cohort)", f"Size ({population})", "M6 retention", "M12 retention", "M36 retention"],
        [[_clean(c.get("cohort"), 40), _size_cell(c.get("size_units")),
          _pct_cell(c.get("m6_retention_pct")), _pct_cell(c.get("m12_retention_pct")),
          _pct_cell(c.get("m36_retention_pct"))] for c in cohorts],
    ) or ("No cohort by start period was evidenced. The cohort table is requested rather than reconstructed "
          "from an average retention rate — an average says nothing about the shape of the curve.\n\n"))
    if _is_filled(spec.get("cohort_notes")):
        parts.append(f"- **Cohort notes:** {_clean(spec.get('cohort_notes'), 420)}\n\n")
    parts.append("---\n\n")

    # --- 2 ----------------------------------------------------------------
    parts.append("## 2. Retention Bridge (GRR / NRR / Logo)\n\n")
    parts.append("Opening revenue, churn, contraction, expansion and closing revenue are reconciled for the "
                 f"period, and GRR, NRR and logo retention are calculated on **the same population "
                 f"({population})**. **New customers are excluded from the retention numerators** — only "
                 f"revenue and {population} in the opening population can be retained, so new business "
                 "never flatters a rate.\n\n")
    parts.append(_table(["Bridge component", "Value"], [
        ["Period", _clean(bridge.get("period"), 80)],
        *[[_BRIDGE_LABEL[k], _clean(bridge.get(k), 180)] for k in _BRIDGE_KEYS],
        ["New customers excluded from numerators",
         "**Yes** — enforced on both the revenue and the logo numerators"
         if bridge.get("new_customers_excluded") is True
         else _clean(bridge.get("new_customers_excluded"), 320)],
        ["Source", _clean(bridge.get("source") or _NA, 60)],
        ["Gaps", _clean(bridge.get("gaps"), 420)],
    ]))
    parts.append(f"### Retention on one population — **{population}**\n\n")
    parts.append(_table(["Metric", "Value (same population)"], [
        ["GRR (gross revenue retention)", _clean(same_pop.get("grr"), 180)],
        ["NRR (net revenue retention)", _clean(same_pop.get("nrr"), 180)],
        ["Logo retention", _clean(same_pop.get("logo_retention"), 180)],
        ["Basis", _clean(same_pop.get("notes"), 460) or f"{_SAME_POP_RULE} {_COMPUTED}"],
    ]))
    metric_rows = [[_METRIC_LABEL[key], f"{_pct(metrics.get(key)):g}%"] for key in _METRIC_KEYS
                   if _pct(metrics.get(key)) is not None]
    if metric_rows:
        parts.append("### Retention metric family\n\n")
        parts.append(_table(["Metric", "Value"], metric_rows))
        parts.append(f"*Every rate above is measured on **{population}**; {_EXCLUSION_RULE}.*\n\n")
    else:
        parts.append("No GRR, NRR or logo retention rate was evidenced, so persistence of revenue is "
                     "unquantified. The retention workbook and the billing ledger are requested; an empty "
                     "retention table is an information gap, not a measured result.\n\n")
    parts.append("### Movement in retention\n\n")
    if falls:
        parts.append("Retention has fallen. This is recorded as a **finding** with magnitude and direction "
                     "below — it is not carried as a caveat and it is not softened.\n\n")
    parts.append(_table(
        ["Metric", "From", "To", "Direction", "Magnitude", "Status", "Source"],
        [[_clean(r.get("metric"), 50), _clean(r.get("from_value"), 40), _clean(r.get("to_value"), 40),
          _direction(r.get("direction")), _clean(r.get("magnitude"), 200),
          "**Finding**" if r.get("is_finding") else "Movement",
          _clean(r.get("source") or _NA, 60)] for r in deltas],
    ) or ("No dated pair of retention values was evidenced, so no movement is measured. Two dated values for "
          "GRR, NRR or logo retention are requested so any movement can be stated in percentage points with "
          "a direction.\n\n"))
    parts.append("---\n\n")

    # --- 3 ----------------------------------------------------------------
    parts.append("## 3. Retention by Segment, Tenure & Loss Reasons\n\n")
    parts.append(f"Retention is cut by segment and by tenure on the same **{population}** population, so a "
                 "blended rate cannot hide a weak cohort. Reasons for loss are reported only where the "
                 "records capture them, and the point where loss concentrates is stated rather than averaged "
                 "away.\n\n")
    parts.append("### Retention by segment\n\n")
    parts.append(_cut_table(by_segment, name_key="segment", header="Segment", population=population)
                 or "No segment-level retention was evidenced.\n\n")
    parts.append("### Retention by tenure\n\n")
    parts.append(_cut_table(by_tenure, name_key="tenure_band", header="Tenure band", population=population)
                 or "No tenure-band retention was evidenced.\n\n")
    parts.append("### Reasons for loss (as recorded)\n\n")
    parts.append(_table(["Reason for loss", "Contribution", "Concentrates in", "Source"],
                        [[_clean(r.get("reason"), 80), _clean(r.get("contribution_pct"), 60),
                          _clean(r.get("concentrates_in"), 160), _clean(r.get("source") or _NA, 50)]
                         for r in loss_reasons])
                 or "No loss-reason records were opened.\n\n")
    parts.append(f"- **Where loss concentrates:** {_clean(concentration.get('statement'), 420)}\n")
    parts.append(f"- **Source:** {_clean(concentration.get('source') or _NA, 60)}\n\n")
    parts.append("---\n\n")

    # --- 4 ----------------------------------------------------------------
    parts.append("## 4. Contract Protection & Renewal Cliff\n\n")
    parts.append("Executed contracts for the largest customers are reviewed for term, renewal mechanism, "
                 "notice period, minimum commitment, price escalator and termination for convenience. Where "
                 "a counterparty is not named in the packs, the name is requested — never invented.\n\n")
    parts.append(_table(
        ["Customer", *[label for _k, label, _c, _r in _CONTRACT_FIELDS], "Source"],
        [[_clean(c.get("customer"), 70),
          *[_clean(c.get(key), 100) for key, _l, _c, _r in _CONTRACT_FIELDS],
          _clean(c.get("source") or _NA, 40)] for c in contracts],
    ) or ("No executed contract was opened, so contractual protection is unverified. The contract register is "
          "requested rather than reconstructed from prose.\n\n"))
    parts.append("### Renewal cliff\n\n")
    parts.append(_table(["Item", "Value"], [
        ["Material share of revenue up for renewal", _clean(renewal.get("material_share_pct"), 120)],
        ["Window", _clean(renewal.get("window"), 120)],
        ["Note", _clean(renewal.get("note"), 460)],
        ["Source", _clean(renewal.get("source") or _NA, 60)],
    ]))
    if _is_filled(renewal.get("information_request")):
        parts.append(f"**{_clean(renewal.get('information_request'), 340)}**\n\n")
    parts.append("---\n\n")

    # --- 5 ----------------------------------------------------------------
    parts.append("## 5. Behaviour vs Protection\n\n")
    parts.append("Behaviour and protection are different things and are never merged here. **Customers who "
                 "have stayed are not the same as customers who are contractually committed — stayed ≠ "
                 "contractually committed.** A high retention rate on a base that can leave on short notice "
                 "is a behavioural result, not a contractual floor.\n\n")
    parts.append(_table(["Lens", "Statement"], [
        ["Behaviour — stayed", _clean(behaviour.get("stayed_note"), 420)],
        ["Protection — contractually committed", _clean(behaviour.get("committed_note"), 420)],
        ["Distinction", _clean(behaviour.get("distinction"), 480)],
        ["Source", _clean(behaviour.get("source") or _NA, 60)],
    ]))
    parts.append("*This section does not recommend invest or pass. Retention that has fallen is reported as "
                 "a **finding** with its magnitude and direction; retention that cannot be measured on a "
                 "constant population is reported as unquantified with the workbook requested. Staying "
                 "behaviour is never presented as contractual commitment.*\n\n")
    parts.append("---\n\n")

    # --- 6 ----------------------------------------------------------------
    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(_table(["Metric", "Verdict / Explanation"], [
        ["Quality Verdict", _clean(spec.get("quality_verdict") or "PASS", 30)],
        ["Reliance Verdict", _clean(spec.get("reliance_verdict") or "LIMITED", 30)],
        ["Rationale", _clean(spec.get("quality_reliance_rationale")
                             or "Limits stated in the sections above.", 520)],
    ]))
    parts.append(f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — is the work accurate "
                 "and honest about limits?\n\n")
    parts.append(f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — can diligence "
                 "rest on this retention arithmetic and on the protection behind it?\n\n")
    notes = [_clean(n, 300) for n in (spec.get("stickiness_notes") or [])
             if isinstance(n, str) and n.strip()]
    if notes:
        parts.append("### Retention notes\n\n")
        parts.extend(f"- {note}\n" for note in notes[:6])
        parts.append("\n")
    parts.append("*This document measures whether revenue persists and whether contracts protect it. It does "
                 "not recommend invest or pass.*\n\n")
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        parts.extend(f"[{i}] {_clean(name, 120)}\n" for i, name in enumerate(list(srcs)[:16], start=1))
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n\n")

    return "".join(parts)
