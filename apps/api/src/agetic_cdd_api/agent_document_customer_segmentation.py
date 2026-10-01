"""Compose DiligenceIQ Customer Segmentation — calculated concentration (prompt book).

Shows where revenue comes from and how exposed it is to a small number of customers.
Concentration is the single largest value driver an IC argues about, so it is
**calculated** from parent-level revenue shares — never described. Pointers to the
billing ledger or investor workbook are resolved first and a customer-level view is
built with account, parent and location identifiers. Revenue is segmented by service,
customer type, geography and contract form, and each axis is reconciled to the revenue
total in the accounts with any unclassified remainder shown rather than forced into a
segment. The largest contracts are named with value, share of revenue, end date and
termination rights.

Every count states the population it refers to — accounts, parents, locations or
subscriptions — and populations are never mixed in one table.

Where the ledger is missing, concentration is **unassessed**: the ledger is requested
and any risk rating is withheld. An empty table is not high risk.

No invest/pass. No company allowlists. Preserves the legacy Ideal Customer Profile
(ICP) shape (segments / geo_mix / icp_notes) for decks.
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
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")

_UNASSESSED = (
    "Concentration is unassessed (it is not calculable from the packs opened) — "
    "an empty concentration table is not a high-risk finding."
)
_WITHHELD = "withheld"

_DOCUMENT_TITLE = "Ideal Customer Profile (ICP)"
_DD_CODE = "DD-08"

_POPULATIONS = ("accounts", "parents", "locations", "subscriptions")
_AXES = ("service", "customer_type", "geography", "contract_form")
_AXIS_LABEL = {
    "service": "Service / product line",
    "customer_type": "Customer type",
    "geography": "Geography",
    "contract_form": "Contract form",
}

# ---------------------------------------------------------------------------
# ledger / grain cues
# ---------------------------------------------------------------------------

_LEDGER_CUE = re.compile(
    r"\b(billing\s+ledger|customer\s+ledger|sales\s+ledger|revenue\s+ledger|"
    r"subscription\s+ledger|debtors?\s+ledger|aged\s+debtors?|"
    r"accounts?\s+receivable\s+ledger|AR\s+ledger|invoice\s+register|"
    r"invoice\s+listing|billing\s+system|billing\s+data|"
    r"investor\s+workbook|investor\s+model|revenue\s+workbook|"
    r"customer\s+workbook|customer\s+master|customer\s+file|"
    r"revenue\s+by\s+customer|customer[- ]level\s+(?:revenue|data|detail)|"
    r"transaction[- ]level\s+(?:revenue|data)|sales\s+by\s+customer)\b",
    re.IGNORECASE,
)
_LEDGER_POINTER_CUE = re.compile(
    r"\b(?:see|refer(?:\s+to)?|per|available\s+(?:in|at)|provided\s+in|"
    r"attached|appendix|annex(?:ure)?|tab\b|sheet\b|folder|index\s+ref)\b",
    re.IGNORECASE,
)
_LEDGER_MISSING_CUE = re.compile(
    r"\b(not\s+(?:yet\s+)?(?:provided|available|supplied|shared|uploaded)|"
    r"outstanding\s+request|to\s+be\s+provided|pending\s+(?:upload|provision)|"
    r"withheld|redacted|anonymis(?:ed|ation)|no\s+customer[- ]level\s+data|"
    r"aggregated\s+only|not\s+in\s+the\s+data\s+room)\b",
    re.IGNORECASE,
)
_GRAIN_ACCOUNT = re.compile(
    r"\b(account\s+(?:id|ids|number|numbers|code|codes|reference)|"
    r"customer\s+(?:id|ids|number|numbers|code|codes)|debtor\s+code)\b",
    re.IGNORECASE,
)
_GRAIN_PARENT = re.compile(
    r"\b(parent\s+(?:id|ids|company|group|entity|account)|ultimate\s+parent|"
    r"group\s+(?:id|ids|code|hierarchy)|corporate\s+hierarchy|"
    r"parent[- ]child|top\s+parent|group\s+parent)\b",
    re.IGNORECASE,
)
_GRAIN_LOCATION = re.compile(
    r"\b(location\s+(?:id|ids|code|codes)|site\s+(?:id|ids|code|codes)|"
    r"ship[- ]to|branch\s+(?:id|code)|store\s+(?:id|code)|premises\s+(?:id|ref))\b",
    re.IGNORECASE,
)
_GRAIN_SUBSCRIPTION = re.compile(
    r"\b(subscription\s+(?:id|ids|line|lines|level)|contract\s+(?:id|ids|line)|"
    r"licen[cs]e\s+(?:id|key|line)|seat\s+(?:id|level)|SKU\s+line)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# population counts
# ---------------------------------------------------------------------------

_COUNT_ACCOUNTS = re.compile(
    r"(?:([\d,]{1,12})\s*(?:k\b|thousand)?\s*(?:active\s+|billing\s+|paying\s+|"
    r"live\s+)?(?:customer\s+)?accounts?\b"
    r"|(?:customer\s+)?accounts?\s*(?:base\s*)?(?:of|:|=|totall?ing|numbered?)\s*"
    r"(?:~|≈)?\s*([\d,]{1,12}))",
    re.IGNORECASE,
)
_COUNT_PARENTS = re.compile(
    r"(?:([\d,]{1,12})\s*(?:parent|parent\s+group|ultimate\s+parent|"
    r"customer\s+group|group)s?\b"
    r"|(?:parent\s+groups?|parents?|ultimate\s+parents?|customer\s+groups?)\s*"
    r"(?:of|:|=|totall?ing|numbered?)\s*(?:~|≈)?\s*([\d,]{1,12}))",
    re.IGNORECASE,
)
_COUNT_LOCATIONS = re.compile(
    r"(?:([\d,]{1,12})\s*(?:locations?|sites?|premises|branches|stores?|outlets?|"
    r"depots?|ship[- ]to\s+points?)\b"
    r"|(?:locations?|sites?|branches|stores?)\s*"
    r"(?:of|:|=|totall?ing|numbered?)\s*(?:~|≈)?\s*([\d,]{1,12}))",
    re.IGNORECASE,
)
_COUNT_SUBSCRIPTIONS = re.compile(
    r"(?:([\d,]{1,12})\s*(?:subscriptions?|licen[cs]es?|seats?|"
    r"live\s+contracts?|active\s+contracts?|service\s+lines?)\b"
    r"|(?:subscriptions?|licen[cs]es?|seats?|live\s+contracts?)\s*"
    r"(?:of|:|=|totall?ing|numbered?)\s*(?:~|≈)?\s*([\d,]{1,12}))",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# concentration cues
# ---------------------------------------------------------------------------

_CUSTOMER_NOUN = (
    r"customers?|clients?|accounts?|parents?|parent\s+groups?|groups?|"
    r"relationships?|contracts?|counterparties"
)
_TOP_N_SHARE = re.compile(
    rf"top[\s\-]*(\d{{1,2}})\s*(?:{_CUSTOMER_NOUN})\b"
    r"[^.\d%]{0,50}?(?:~|≈)?(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_SHARE_TOP_N = re.compile(
    r"(?:~|≈)?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:total\s+|group\s+|FY\d{2}\s+)?"
    rf"(?:revenue|turnover|sales|billings|income)\b[^.\d%]{{0,40}}?top[\s\-]*(\d{{1,2}})\s*(?:{_CUSTOMER_NOUN})",
    re.IGNORECASE,
)
_TOP_1_SHARE = re.compile(
    r"(?:single\s+)?(?:largest|biggest|leading|number\s+one|no\.?\s*1)\s+"
    rf"(?:{_CUSTOMER_NOUN})\b[^.\d%]{{0,50}}?(?:~|≈)?(\d{{1,3}}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_SHARE_TOP_1 = re.compile(
    r"(?:~|≈)?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:total\s+|group\s+)?"
    r"(?:revenue|turnover|sales|billings)\b[^.\d%]{0,40}?"
    rf"(?:single\s+)?(?:largest|biggest|leading)\s+(?:{_CUSTOMER_NOUN})",
    re.IGNORECASE,
)
_RANKED_SHARE = re.compile(
    r"\b(?:customer|client|account|parent|group)\s*(?:#|no\.?\s*)?(\d{1,2})\b"
    r"[^.\d%]{0,40}?(?:~|≈)?(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_ORDINAL_SHARE = re.compile(
    r"\b(second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+"
    rf"(?:largest|biggest)\s+(?:{_CUSTOMER_NOUN})\b"
    r"[^.\d%]{0,40}?(?:~|≈)?(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_ORDINAL_RANK = {
    "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_HHI = re.compile(
    r"\b(?:HHI|Herfindahl(?:[- ]Hirschman)?(?:\s+index)?|"
    r"concentration\s+index|Gini(?:\s+coefficient)?)\b"
    r"[^.\d]{0,30}(?:~|≈)?([\d,]{1,7}(?:\.\d+)?)",
    re.IGNORECASE,
)
_GROSS_PROFIT_CUE = re.compile(
    r"\b(gross\s+profit|gross\s+margin|GP\b|contribution\s+margin|"
    r"margin\s+by\s+customer|customer\s+profitability)\b",
    re.IGNORECASE,
)
_QUALITATIVE_CONCENTRATION = re.compile(
    r"\b(highly\s+concentrated|high(?:ly)?\s+concentration|"
    r"concentration\s+(?:risk|is\s+high|is\s+material)|"
    r"significant(?:ly)?\s+concentrat\w*|material\s+concentration|"
    r"heavily\s+(?:reliant|dependent)\s+on\s+(?:a\s+)?(?:few|small\s+number|"
    r"handful|single)|reliant\s+on\s+a\s+(?:few|small\s+number|handful)|"
    r"customer\s+concentration|key[- ]account\s+dependency|"
    r"dependen(?:t|cy)\s+on\s+(?:a\s+)?(?:few|handful|single|small\s+number))\b",
    re.IGNORECASE,
)
_PARENT_AGGREGATION_CUE = re.compile(
    r"\b(parent\s+level|parent[- ]level|aggregated\s+to\s+(?:the\s+)?parent|"
    r"group(?:ed)?\s+(?:to|at)\s+(?:the\s+)?(?:parent|group)\s+level|"
    r"ultimate\s+parent|consolidated\s+(?:to\s+)?(?:parent|group)|"
    r"related\s+accounts?\s+(?:are\s+)?combined)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# segment axis vocabularies
# ---------------------------------------------------------------------------

_SERVICE_VOCAB = re.compile(
    r"\b(service|services|product|products|product\s+line|offering|offerings|"
    r"solution|solutions|module|modules|platform|software|SaaS|licen[cs]e|"
    r"licensing|hardware|equipment|device|devices|maintenance|installation|"
    r"support|consult(?:ing|ancy)|advisory|managed\s+service|"
    r"implementation|training|repairs?|spares?|aftermarket|logistics|"
    r"freight|warehousing|leasing|rental|subscription|transaction|"
    r"interchange|processing|data|analytics|media|advertising|"
    r"manufactur(?:e|ing)|distribution|wholesale|retail|core|ancillary)\b",
    re.IGNORECASE,
)
_CUSTOMER_TYPE_VOCAB = re.compile(
    r"\b(enterprise|large\s+enterprise|corporate|mid[- ]market|midmarket|"
    r"SME|SMB|small\s+business|micro\s+business|consumer|retail\s+customer|"
    r"B2B|B2C|B2B2C|public\s+sector|government|municipal|local\s+authority|"
    r"NHS|education|university|school|healthcare|hospital|"
    r"OEM|tier[- ]?[12]|distributor|reseller|dealer|channel\s+partner|"
    r"wholesaler|fleet|institutional|professional|prosumer|individual|"
    r"residential|commercial|industrial|not[- ]for[- ]profit|charity|"
    r"third[- ]party|intercompany|blue[- ]chip|key\s+account|"
    r"national\s+account|regional\s+account|new\s+customer|"
    r"existing\s+customer|student|graduate|worker|operator|user|household)\b",
    re.IGNORECASE,
)
_GEO_NAME_VOCAB = re.compile(
    r"\b(north|south|east|west|central|northern|southern|eastern|western|"
    r"midlands?|region|regional|domestic|national|nationwide|international|"
    r"overseas|export|exports|home\s+market|metro|urban|rural|tier[- ]?[123]|"
    r"state|city|county|province|district|territory|"
    r"EMEA|APAC|LATAM|ANZ|MENA|DACH|Nordics?|Benelux|"
    r"UK|United\s+Kingdom|US|USA|United\s+States|EU|Europe|European|"
    r"Asia|Africa|America|Americas|Middle\s+East|"
    r"England|Scotland|Wales|Ireland|India|China|Japan|Germany|France|"
    r"Spain|Italy|Netherlands|Poland|Canada|Mexico|Brazil|Australia|"
    r"Singapore|Malaysia|Indonesia|Vietnam|Thailand|Philippines|"
    r"UAE|Saudi|Qatar|Kenya|Nigeria|South\s+Africa)\b",
    re.IGNORECASE,
)
_CONTRACT_FORM_VOCAB = re.compile(
    r"\b(fixed[- ]price|fixed\s+fee|time\s+and\s+materials|T&M|cost[- ]plus|"
    r"subscription|recurring|annual\s+contract|multi[- ]year|"
    r"rolling(?:\s+contract|\s+monthly)?|evergreen|auto[- ]renew(?:ing|al)?|"
    r"framework(?:\s+agreement)?|call[- ]off|MSA|master\s+services?\s+agreement|"
    r"SLA|spot|ad\s+hoc|ad[- ]hoc|one[- ]off|project|retainer|"
    r"pay[- ]as[- ]you[- ]go|usage[- ]based|consumption|committed|"
    r"take[- ]or[- ]pay|minimum\s+commitment|licen[cs]e|perpetual|term\s+licen[cs]e|"
    r"lease|hire|tender|contracted|non[- ]contracted|uncontracted|"
    r"month[- ]to[- ]month|monthly|quarterly|annually|"
    r"long[- ]term\s+(?:contract|agreement)|short[- ]term\s+(?:contract|agreement))\b",
    re.IGNORECASE,
)
_AXIS_VOCAB: dict[str, re.Pattern[str]] = {
    "service": _SERVICE_VOCAB,
    "customer_type": _CUSTOMER_TYPE_VOCAB,
    "geography": _GEO_NAME_VOCAB,
    "contract_form": _CONTRACT_FORM_VOCAB,
}
_AXIS_SENT_CUE: dict[str, re.Pattern[str]] = {
    "service": re.compile(
        r"\b(by\s+service|by\s+product|service\s+(?:mix|line|split|revenue)|"
        r"product\s+(?:mix|line|split|revenue)|revenue\s+by\s+service|"
        r"revenue\s+by\s+product|revenue\s+mix|split\s+by\s+service)\b",
        re.IGNORECASE,
    ),
    "customer_type": re.compile(
        r"\b(by\s+customer\s+type|customer\s+(?:mix|type|segment|segmentation)|"
        r"by\s+segment|segment\s+(?:mix|split)|customer\s+base\s+split|"
        r"by\s+channel|channel\s+mix|by\s+vertical|vertical\s+mix)\b",
        re.IGNORECASE,
    ),
    "geography": re.compile(
        r"\b(by\s+geograph\w+|geograph\w+\s+(?:mix|split|spread|revenue)|"
        r"by\s+region|regional\s+(?:mix|split|revenue)|by\s+country|"
        r"revenue\s+by\s+(?:region|country|geograph\w+)|geographic\s+concentration)\b",
        re.IGNORECASE,
    ),
    "contract_form": re.compile(
        r"\b(by\s+contract(?:\s+(?:form|type|structure))?|contract\s+"
        r"(?:mix|form|type|structure|profile)|contracted\s+revenue|"
        r"recurring\s+(?:vs|versus)\s+non[- ]recurring|revenue\s+quality\s+split)\b",
        re.IGNORECASE,
    ),
}
_SEGMENT_GENERIC_CUE = re.compile(
    r"\b(segment|segmentation|mix|split|breakdown|composition|"
    r"share\s+of\s+revenue|of\s+revenue|of\s+total\s+revenue)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# row extraction
# ---------------------------------------------------------------------------

_NAME_TOKEN = r"[A-Za-z][A-Za-z0-9&/'’\.\-]*"
_ROW_NAME_PCT = re.compile(
    rf"({_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,4}})\s*"
    r"(?:[:\-–—=]|\(|\bat\b|\bis\b|\bwas\b|\brepresent(?:s|ed)?\b|"
    r"\baccount(?:s|ed)?\s+for\b|\bcontribut(?:es|ed)\b|\bmakes?\s+up\b|\s)\s*"
    r"(?:~|≈|c\.\s*)?(\d{1,3}(?:\.\d+)?)\s*%",
)
_PCT_THEN_NAME = re.compile(
    r"(?:~|≈|c\.\s*)?(\d{1,3}(?:\.\d+)?)\s*%\s*"
    r"(?:of\s+(?:total\s+|group\s+)?(?:revenue|turnover|sales|the\s+mix)\s*)?"
    r"(?:from|in|is|comes\s+from|attributable\s+to|derived\s+from|"
    r"relates\s+to|sits\s+in|generated\s+(?:by|in|from))\s+"
    rf"((?:the\s+)?{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,4}})",
    re.IGNORECASE,
)
_CUSTOMER_COUNT_IN_ROW = re.compile(
    rf"([\d,]{{1,9}})\s*(?:{_CUSTOMER_NOUN})\b",
    re.IGNORECASE,
)
_UNCLASSIFIED_CUE = re.compile(
    r"\b(unclassified|unallocated|unassigned|not\s+(?:yet\s+)?classified|"
    r"other(?:s)?|remainder|residual|balance|miscellaneous|sundry|"
    r"cannot\s+be\s+allocated|no\s+segment\s+tag)\b",
    re.IGNORECASE,
)
_TOTAL_REVENUE = re.compile(
    r"(?:total\s+revenue|group\s+revenue|revenue\s+(?:in|per)\s+the\s+accounts|"
    r"statutory\s+revenue|audited\s+revenue|turnover)"
    r"[^.\d₹$€£]{0,30}?(INR|USD|EUR|GBP|Rs\.?|[₹$€£])?\s*"
    r"(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(cr|crore|lakh|k|m|mn|million|bn|billion)?",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# contract cues
# ---------------------------------------------------------------------------

_MONEY = re.compile(
    r"(INR|USD|EUR|GBP|Rs\.?|[₹$€£])\s*"
    r"(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(cr|crore|lakh|lakhs|k|m|mn|million|bn|billion)?",
    re.IGNORECASE,
)
_MONEY_SCALE = {
    "": 1.0, "k": 1e3, "lakh": 1e5, "lakhs": 1e5, "m": 1e6, "mn": 1e6,
    "million": 1e6, "cr": 1e7, "crore": 1e7, "bn": 1e9, "billion": 1e9,
}
_CURRENCY_ALIAS = {
    "rs": "INR", "rs.": "INR", "₹": "INR", "inr": "INR",
    "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR",
    "£": "GBP", "gbp": "GBP",
}
_DATE = re.compile(
    r"\b((?:FY|CY)\s?(?:19|20)?\d{2}(?:[-–/](?:\d{2}|\d{4}))?|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2}|"
    r"\d{1,2}[/-]\d{1,2}[/-](?:19|20)?\d{2}|"
    r"Q[1-4]\s*(?:FY|CY)?\s?(?:19|20)?\d{2}|"
    r"(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_CONTRACT_CUE = re.compile(
    r"\b(contract|agreement|MSA|master\s+services?\s+agreement|"
    r"framework\s+agreement|statement\s+of\s+work|SOW|"
    r"supply\s+agreement|service\s+agreement|licen[cs]e\s+agreement|"
    r"purchase\s+order|call[- ]off|tender|concession|lease)\b",
    re.IGNORECASE,
)
_CONTRACT_NAMED = re.compile(
    r"(?:contract|agreement|MSA|framework|SOW|relationship|arrangement)\s+"
    r"(?:with|for|held\s+by)\s+"
    r"((?:the\s+)?[A-Z][A-Za-z0-9&'’\.\-]*"
    r"(?:\s+(?:[A-Z][A-Za-z0-9&'’\.\-]*|of|and|the|de|du))*)",
)
_CONTRACT_NAMED_ALT = re.compile(
    r"\b([A-Z][A-Za-z0-9&'’\.\-]*(?:\s+[A-Z][A-Za-z0-9&'’\.\-]*){0,3})\s+"
    r"(?:contract|agreement|MSA|framework|account)\b",
)
_END_DATE_CUE = re.compile(
    r"(?:expir(?:es|y|ing|ation)|end(?:s|ing)?(?:\s+date)?|終|"
    r"terminat(?:es|ing)\s+on|runs?\s+(?:to|until|through)|"
    r"until|through\s+to|renewal\s+date|renews?\s+(?:on|in)|"
    r"contract\s+end|term\s+end(?:s|ing)?)"
    r"[^.\d]{0,20}" + _DATE.pattern,
    re.IGNORECASE,
)
_TERMINATION_CUE = re.compile(
    r"\b(terminat\w*\s+for\s+convenience|termination\s+(?:rights?|clause|"
    r"provisions?|on\s+notice)|right\s+to\s+terminate|"
    r"notice\s+period\s+of\s+[\d]+\s*(?:days?|weeks?|months?)|"
    r"[\d]+\s*(?:days?|weeks?|months?)[’'\s]*\s*notice|"
    r"break\s+(?:clause|right|option)|change\s+of\s+control|"
    r"auto[- ]?renew(?:al|s|ing)?|evergreen|"
    r"exit\s+(?:clause|rights?)|step[- ]in\s+rights?|"
    r"no\s+minimum\s+commitment|cancellable\s+at\s+any\s+time)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

_PLACEHOLDER_NAME = re.compile(
    r"(?i)^(?:tbd|n/?a|unnamed|placeholder|various|customer\s*[a-z]?\d*|"
    r"client\s*[a-z]?\d*|account\s*[a-z]?\d*|company\s*[a-z]?\d*|"
    r"segment\s*\d*|peer\s*\d*|redacted|anonymous|confidential)$"
)
_ROW_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "at", "to", "for", "by", "with",
    "this", "that", "these", "those", "it", "its", "their", "our", "his", "her",
    "revenue", "turnover", "sales", "total", "group", "company", "business",
    "management", "target", "customer", "customers", "client", "clients",
    "account", "accounts", "growth", "margin", "ebitda", "cagr", "year",
    "period", "fy", "cy", "approximately", "about", "circa", "around", "some",
    "roughly", "up", "down", "from", "than", "over", "under", "share", "mix",
    "split", "rate", "value", "volume", "price", "cost", "data", "room",
    "information", "memorandum", "appendix", "annex", "table", "figure",
    "note", "notes", "source", "sources", "ledger", "workbook", "however",
    "overall", "broadly", "materially", "representing", "including",
    "remaining", "balance", "which", "while", "where", "when", "was", "were",
    "is", "are", "be", "been", "has", "have", "had", "will", "would", "may",
    "management’s", "management's", "top", "largest", "biggest", "concentration",
}
_COUNT_SUFFIX = re.compile(r"(?i)\b(k|thousand|m|mn|million)\b")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _insight(text: Any, *, max_chars: int = 520) -> str:
    body = _clean(text, max_chars)
    return f"**Insight Snapshot:** {body}\n\n" if body else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for i in range(len(headers)):
            val = row[i] if i < len(row) else "—"
            cells.append(str(val or "—").replace("|", "\\|").replace("\n", " ").strip())
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _info_request(label: str) -> str:
    return f"Information request: {label} (not stated in the data room)"


def _is_filled(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text == _NA or text.startswith("N/A"):
        return False
    return not text.startswith("Information request")


def _num(raw: Any) -> float | None:
    text = str(raw or "").strip().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _pct_text(value: Any) -> str:
    val = _num(value)
    if val is None:
        return ""
    return f"{val:g}%"


def _pct_or_none(value: Any) -> str | None:
    text = _pct_text(value)
    return text or None


def _count_text(raw: Any, *, context: str = "") -> str:
    """Format a population count, honouring a k/m suffix in the surrounding text."""
    val = _num(raw)
    if val is None:
        return ""
    suffix = _COUNT_SUFFIX.search(context or "")
    if suffix:
        token = suffix.group(1).lower()
        if token in {"k", "thousand"}:
            val *= 1_000
        elif token in {"m", "mn", "million"}:
            val *= 1_000_000
    return _fmt_num(f"{val:g}")


def _population(value: Any, *, default: str = "accounts") -> str:
    text = str(value or "").strip().lower()
    for pop in _POPULATIONS:
        if pop in text or pop.rstrip("s") in text:
            return pop
    if "group" in text or "ultimate" in text:
        return "parents"
    if "site" in text or "branch" in text or "store" in text:
        return "locations"
    if "licen" in text or "seat" in text:
        return "subscriptions"
    return default


def _axis_key(value: Any, *, default: str = "service") -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in _AXES:
        return text
    if "geo" in text or "region" in text or "countr" in text:
        return "geography"
    if "contract" in text or "form" in text or "term" in text:
        return "contract_form"
    if "type" in text or "customer" in text or "vertical" in text or "channel" in text:
        return "customer_type"
    if "service" in text or "product" in text or "offering" in text:
        return "service"
    return default


def _clean_row_name(raw: Any, *, max_chars: int = 48) -> str:
    """Trim a candidate segment/contract name and reject filler."""
    name = _clean(raw, max_chars).strip(" .,;:—–-()")
    name = re.sub(r"(?i)^(?:the|a|an|and|or|of|in|at|to|for|by|with)\s+", "", name)
    name = re.sub(r"(?i)\s+(?:of|in|at|to|for|by|with|and|or|is|was|the)$", "", name)
    name = name.strip(" .,;:—–-")
    if len(name) < 2 or len(name) > max_chars:
        return ""
    if _PLACEHOLDER_NAME.match(name):
        return ""
    tokens = [t for t in re.split(r"\s+", name.lower()) if t]
    if not tokens:
        return ""
    if all(t in _ROW_STOP for t in tokens):
        return ""
    if len(tokens) == 1 and tokens[0] in _ROW_STOP:
        return ""
    if not re.search(r"[A-Za-z]{2}", name):
        return ""
    return name


def _title_case(name: str) -> str:
    if not name:
        return ""
    if name[:1].isupper():
        return name
    return name[:1].upper() + name[1:]


def _soften_concentration(text: Any, *, calculable: bool = False) -> str:
    """Strip asserted concentration-risk language when concentration is not calculated."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if calculable:
        return raw
    out = _QUALITATIVE_CONCENTRATION.sub(
        "customer concentration (not calculated from the ledger)", raw
    )
    if out != raw and "unassessed" not in out.lower():
        out = out.rstrip(" .") + ". " + _UNASSESSED
    return out


def _sum_shares(rows: list[dict[str, Any]]) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        val = _num(row.get("share_pct"))
        if val is None:
            continue
        seen = True
        total += val
    return total if seen else None


def _currency(token: Any) -> str:
    text = str(token or "").strip().lower()
    return _CURRENCY_ALIAS.get(text, text.upper())


def _money_value(
    currency: Any, amount: Any, suffix: Any
) -> tuple[str, float] | None:
    """Return (currency_code, value_in_base_units) for a matched money amount."""
    val = _num(amount)
    if val is None:
        return None
    scale = _MONEY_SCALE.get(str(suffix or "").strip().lower(), 1.0)
    return _currency(currency), val * scale


def _revenue_total(corpus: str) -> str:
    m = _TOTAL_REVENUE.search(corpus or "")
    if not m:
        return ""
    value = _fmt_num(m.group(2), m.group(3) or "")
    return f"{_clean(m.group(0), 80)} (~{value}) {_DOC_CITE}"


def _revenue_total_value(corpus: str) -> tuple[str, float] | None:
    m = _TOTAL_REVENUE.search(corpus or "")
    if not m:
        return None
    return _money_value(m.group(1), m.group(2), m.group(3))


# ---------------------------------------------------------------------------
# concentration calculability
# ---------------------------------------------------------------------------


def _concentration_calculable(
    top_1: Any = None,
    top_5: Any = None,
    top_10: Any = None,
    *,
    ledger_status: str | None = None,
    population: str | None = None,
    corpus: str = "",
    gross_profit_top_1: Any = None,
    gross_profit_top_5: Any = None,
) -> tuple[bool, str]:
    """Return ``(calculable, notes)`` for the concentration table.

    Concentration is calculable only where at least one parent-level top-N revenue
    share is evidenced numerically and the shares are internally coherent
    (0–100%, monotonically non-decreasing from top 1 to top 10). Qualitative prose
    such as "highly concentrated" is **not** a calculation: it leaves concentration
    unassessed, the ledger is requested and any risk rating is withheld. An empty
    concentration table is not a high-risk finding.
    """
    values = {
        "top 1": _num(top_1),
        "top 5": _num(top_5),
        "top 10": _num(top_10),
    }
    gp_values = {
        "gross profit top 1": _num(gross_profit_top_1),
        "gross profit top 5": _num(gross_profit_top_5),
    }
    present = {k: v for k, v in values.items() if v is not None}
    fails: list[str] = []
    notes_bits: list[str] = []

    status = (ledger_status or "").strip().lower()
    if status == "missing":
        fails.append(
            "the billing ledger / investor workbook is not resolved, so parent-level "
            "revenue shares cannot be computed"
        )
    elif status == "partial":
        notes_bits.append(
            "ledger resolved only in part — shares below are limited to the rows that "
            "were opened"
        )

    if not present:
        if _QUALITATIVE_CONCENTRATION.search(corpus or ""):
            fails.append(
                "the packs describe concentration qualitatively but give no top-N "
                "revenue share, and description is not a calculation"
            )
        else:
            fails.append("no top 1 / top 5 / top 10 revenue share is evidenced")

    for label, val in present.items():
        if val < 0 or val > 100:
            fails.append(f"{label} share of {val:g}% is outside 0–100%")

    ordered = [values["top 1"], values["top 5"], values["top 10"]]
    labelled = ["top 1", "top 5", "top 10"]
    prev_val: float | None = None
    prev_label = ""
    for label, val in zip(labelled, ordered):
        if val is None:
            continue
        if prev_val is not None and val + 0.05 < prev_val:
            fails.append(
                f"{label} share ({val:g}%) is below {prev_label} ({prev_val:g}%) — "
                "cumulative shares cannot decrease"
            )
        prev_val, prev_label = val, label

    pop = _population(population, default="parents")
    if pop != "parents":
        notes_bits.append(
            f"shares are stated on {pop}, not parents — related accounts must be "
            "aggregated to parent level before the shares are relied on"
        )

    if fails:
        return False, (
            "Concentration not calculable: " + "; ".join(fails[:4]) + ". " + _UNASSESSED
        )

    computed = ", ".join(f"{label} {val:g}%" for label, val in present.items())
    gp_present = {k: v for k, v in gp_values.items() if v is not None}
    if gp_present:
        notes_bits.append(
            "gross profit concentration also computed ("
            + ", ".join(f"{label} {val:g}%" for label, val in gp_present.items())
            + ")"
        )
    else:
        notes_bits.append(
            "gross profit concentration not computed — customer-level margin data were "
            "not opened"
        )
    tail = ("; " + "; ".join(notes_bits)) if notes_bits else ""
    return True, (
        f"Concentration calculated on parent-level revenue shares: {computed} "
        f"{_COMPUTED}{tail}"
    )


def _risk_rating(
    *,
    calculable: bool,
    top_1: Any = None,
    top_5: Any = None,
    top_10: Any = None,
) -> str | None:
    """Band the calculated concentration; withhold entirely when not calculable."""
    if not calculable:
        return _WITHHELD
    t1, t5, t10 = _num(top_1), _num(top_5), _num(top_10)
    anchor = t5 if t5 is not None else (t10 if t10 is not None else t1)
    if anchor is None:
        return _WITHHELD
    basis_bits = []
    if t1 is not None:
        basis_bits.append(f"top 1 {t1:g}%")
    if t5 is not None:
        basis_bits.append(f"top 5 {t5:g}%")
    if t10 is not None:
        basis_bits.append(f"top 10 {t10:g}%")
    basis = ", ".join(basis_bits) or "calculated shares"

    if t1 is not None and t1 >= 25:
        band = "Elevated"
    elif t5 is not None and t5 >= 60:
        band = "Elevated"
    elif t5 is not None and t5 >= 35:
        band = "Moderate"
    elif t10 is not None and t10 >= 60:
        band = "Moderate"
    elif anchor >= 60:
        band = "Elevated"
    elif anchor >= 35:
        band = "Moderate"
    else:
        band = "Contained"
    return (
        f"{band} — banded from the calculated parent-level shares ({basis}); "
        f"thresholds: top 1 ≥25% or top 5 ≥60% elevated, top 5 ≥35% moderate {_COMPUTED}"
    )


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_customer_segmentation_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "customer": 0,
        "financial": 1,
        "deal_strategy": 2,
        "market_competition": 3,
        "operations": 4,
        "company_management": 5,
    }
    needles = (
        "customer", "segment", "commercial", "concentration", "ledger",
        "billing", "workbook", "thesis", "retention", "valuation",
        "revenue", "contract", "account",
    )
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple[int, int, str]:
        name = str(d.get("filename") or "").lower()
        needle_hit = 0 if any(n in name for n in needles) else 1
        return (
            prefer.get(str(d.get("cdl_category") or ""), 9),
            needle_hit,
            str(d.get("filename") or ""),
        )

    ranked = sorted(docs, key=_rank)
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:12]:
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
        body = loaded.get("text")
        if isinstance(body, str) and body.strip():
            text = body
        elif body is not None:
            text = str(body)
        if not text.strip():
            excerpt = doc.get("excerpt")
            if isinstance(excerpt, str) and excerpt.strip():
                text = excerpt
            elif excerpt is not None:
                text = str(excerpt)
        text = _ZWSP.sub("", text)
        text = _PDF_BULLETS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


# ---------------------------------------------------------------------------
# heuristic — ledger resolution
# ---------------------------------------------------------------------------


def _extract_ledger_resolution(corpus: str) -> dict[str, str]:
    text = corpus or ""
    sents = _sentences(text)
    ledger_sents = [s for s in sents if _LEDGER_CUE.search(s)]
    hit = ledger_sents[0] if ledger_sents else ""

    grain_bits: list[str] = []
    blob = " ".join(ledger_sents) if ledger_sents else text
    for label, pattern in (
        ("account", _GRAIN_ACCOUNT),
        ("parent", _GRAIN_PARENT),
        ("location", _GRAIN_LOCATION),
        ("subscription", _GRAIN_SUBSCRIPTION),
    ):
        if pattern.search(blob):
            grain_bits.append(label)

    missing_flag = bool(
        _LEDGER_MISSING_CUE.search(blob) if ledger_sents else _LEDGER_MISSING_CUE.search(text)
    )
    pointer_only = bool(hit and _LEDGER_POINTER_CUE.search(hit) and not grain_bits)

    if not hit:
        status = "missing"
    elif missing_flag or not grain_bits or pointer_only:
        status = "partial"
    elif "parent" in grain_bits and "account" in grain_bits:
        status = "resolved"
    else:
        status = "partial"

    if grain_bits:
        grain = (
            "Customer-level grain available on: "
            + ", ".join(f"{g} ID" for g in grain_bits)
            + f" {_DOC_CITE}"
        )
        if "parent" not in grain_bits:
            grain += (
                " — parent identifier is not present, so related accounts cannot yet "
                "be rolled up for concentration"
            )
    else:
        grain = _info_request(
            "customer-level grain of the ledger — whether account, parent and location "
            "identifiers are present so related accounts can be rolled up"
        )

    if status == "missing":
        notes = (
            "No billing ledger, customer ledger or investor workbook pointer was found "
            f"in the packs opened. {_UNASSESSED}"
        )
    elif status == "partial":
        parts = [f"{_clean(hit, 200)} {_DOC_CITE}"] if hit else []
        if missing_flag:
            parts.append(
                "the pack records the customer-level data as not provided, redacted or "
                "aggregated only"
            )
        if pointer_only:
            parts.append(
                "the reference is a pointer rather than the ledger itself, so the "
                "underlying rows were not opened"
            )
        if not grain_bits:
            parts.append("no account / parent / location identifiers are described")
        notes = "Ledger resolved only in part: " + "; ".join(parts) + "."
    else:
        notes = (
            f"{_clean(hit, 220)} {_DOC_CITE} — opened as the customer-level source for "
            "segmentation and concentration."
        )

    if status == "resolved":
        info = ""
    else:
        info = _info_request(
            "the billing ledger or investor workbook at customer level for the audited "
            "period, with account ID, parent ID, location ID, revenue and — where held "
            "— gross profit per row"
        )

    return {
        "status": status,
        "source_doc": (
            f"{_clean(hit, 160)} {_DOC_CITE}"
            if hit
            else _info_request("name and location of the billing ledger / investor workbook")
        ),
        "grain": grain,
        "notes": notes,
        "information_request": info,
        "source": _DOC_CITE if hit else _NA,
    }


# ---------------------------------------------------------------------------
# heuristic — customer universe
# ---------------------------------------------------------------------------


def _first_count(pattern: re.Pattern[str], corpus: str) -> str:
    for m in pattern.finditer(corpus or ""):
        raw = next((g for g in m.groups() if g), "")
        if not raw:
            continue
        context = (corpus or "")[m.start() : m.end() + 24]
        value = _count_text(raw, context=context)
        if not value:
            continue
        return f"{value} {_DOC_CITE}"
    return ""


def _extract_customer_universe(corpus: str, *, ledger_status: str) -> dict[str, str]:
    accounts = _first_count(_COUNT_ACCOUNTS, corpus)
    parents = _first_count(_COUNT_PARENTS, corpus)
    locations = _first_count(_COUNT_LOCATIONS, corpus)
    subscriptions = _first_count(_COUNT_SUBSCRIPTIONS, corpus)

    if parents:
        primary = "parents"
    elif accounts:
        primary = "accounts"
    elif subscriptions:
        primary = "subscriptions"
    elif locations:
        primary = "locations"
    else:
        primary = "accounts"

    filled = [x for x in (accounts, parents, locations, subscriptions) if x]
    if filled:
        label = (
            f"Primary population for revenue and segment counts: **{primary}**. "
            f"{len(filled)} of 4 populations are evidenced; the remainder are named as "
            f"information requests rather than inferred from each other {_COMPUTED}"
        )
    else:
        label = _info_request(
            "customer universe counts — number of accounts, parents, locations and "
            "subscriptions, each stated separately"
        )
        if ledger_status == "missing":
            label += (
                " — the counts follow from the ledger, which is not yet resolved"
            )

    return {
        "accounts_n": accounts or _info_request("number of customer accounts in the ledger"),
        "parents_n": parents or _info_request(
            "number of parent groups once related accounts are rolled up"
        ),
        "locations_n": locations or _info_request(
            "number of customer locations / sites served"
        ),
        "subscriptions_n": subscriptions or _info_request(
            "number of live subscriptions / contract lines"
        ),
        "population_label": label,
        "source": _DOC_CITE if filled else _NA,
    }


# ---------------------------------------------------------------------------
# heuristic — segments by axis
# ---------------------------------------------------------------------------


def _axis_candidate_rows(
    corpus: str,
    axis: str,
) -> tuple[list[dict[str, Any]], float | None]:
    """Return (rows, explicit_unclassified_pct) for one segmentation axis."""
    vocab = _AXIS_VOCAB[axis]
    axis_cue = _AXIS_SENT_CUE[axis]
    sents = _sentences(corpus)
    scoped = [
        s for s in sents
        if axis_cue.search(s) or (vocab.search(s) and _SEGMENT_GENERIC_CUE.search(s))
    ]
    if not scoped:
        scoped = [s for s in sents if vocab.search(s) and "%" in s]

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    unclassified: float | None = None

    def _accept(name: str, pct: Any, sent: str) -> None:
        nonlocal unclassified
        cleaned = _clean_row_name(name)
        if not cleaned:
            return
        val = _num(pct)
        if val is None or val < 0 or val > 100:
            return
        if _UNCLASSIFIED_CUE.match(cleaned) or _UNCLASSIFIED_CUE.fullmatch(cleaned):
            if unclassified is None:
                unclassified = val
            return
        if not vocab.search(cleaned) and axis != "geography":
            return
        if axis == "geography" and not (
            vocab.search(cleaned) or (cleaned[:1].isupper() and axis_cue.search(sent))
        ):
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        count_m = _CUSTOMER_COUNT_IN_ROW.search(sent)
        gp_share = None
        if _GROSS_PROFIT_CUE.search(sent):
            gp_candidates = [
                _num(x) for x in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", sent)
            ]
            gp_candidates = [c for c in gp_candidates if c is not None and c != val]
            if gp_candidates:
                gp_share = gp_candidates[0]
        row: dict[str, Any] = {
            "name": _title_case(cleaned),
            "revenue": (
                f"{_pct_text(val)} of revenue {_DOC_CITE}"
            ),
            "share_pct": _pct_text(val),
            "customer_count": (
                f"{_count_text(count_m.group(1), context=count_m.group(0))} "
                f"{_DOC_CITE}"
                if count_m
                else _info_request("customer count for this segment, on a stated population")
            ),
        }
        if gp_share is not None:
            row["gp_share_pct"] = _pct_text(gp_share)
        rows.append(row)

    for sent in scoped:
        for m in _ROW_NAME_PCT.finditer(sent):
            _accept(m.group(1), m.group(2), sent)
        for m in _PCT_THEN_NAME.finditer(sent):
            _accept(m.group(2), m.group(1), sent)
        if len(rows) >= 8:
            break

    # An explicit unclassified / other row anywhere in the axis scope counts.
    if unclassified is None:
        for sent in scoped:
            if not _UNCLASSIFIED_CUE.search(sent):
                continue
            for m in re.finditer(
                r"(?i)(unclassified|unallocated|unassigned|other|remainder|residual|"
                r"balance|sundry)[^.\d%]{0,24}(\d{1,3}(?:\.\d+)?)\s*%",
                sent,
            ):
                unclassified = _num(m.group(2))
                break
            if unclassified is not None:
                break

    return rows[:8], unclassified


def _reconcile_notes(
    axis: str,
    rows: list[dict[str, Any]],
    *,
    unclassified_pct: float | None,
    revenue_total: str,
) -> tuple[str, str]:
    """Return (unclassified_share_pct, reconcile_notes) for an axis."""
    total = _sum_shares(rows)
    label = _AXIS_LABEL.get(axis, axis)
    base = (
        f"Revenue total in the accounts: {revenue_total}"
        if revenue_total
        else _info_request(
            "revenue total in the accounts for the same period, to reconcile the "
            f"{label.lower()} split against"
        )
    )
    if total is None:
        return (
            _info_request(f"revenue share by {label.lower()}"),
            (
                f"No {label.lower()} revenue shares were evidenced, so nothing is "
                f"reconciled and no remainder is implied. {base}"
            ),
        )

    declared = unclassified_pct
    if total > 100.5:
        note = (
            f"{label} shares sum to {total:g}% — above 100%, so the rows overlap, "
            "double-count parents, or use a different denominator from the accounts. "
            "The split is shown as stated and is not normalised; reconciliation to the "
            f"accounts total is required before use. {base} {_COMPUTED}"
        )
        share = (
            f"{_pct_text(declared)} stated"
            if declared is not None
            else "Not applicable — shares already exceed 100%"
        )
        return share, note

    remainder = 100.0 - total
    if declared is not None:
        share_txt = f"{_pct_text(declared)} {_DOC_CITE}"
        gap = remainder - declared
        note = (
            f"{label} rows sum to {total:g}% of revenue; the pack states an "
            f"unclassified / other remainder of {declared:g}%. "
            + (
                f"A further {gap:g}% is neither classified nor declared and is left "
                "unallocated rather than forced into a segment. "
                if gap > 0.5
                else "Rows plus the declared remainder reconcile to the accounts total. "
            )
            + f"{base} {_COMPUTED}"
        )
        return share_txt, note

    if remainder > 0.5:
        share_txt = f"{remainder:g}% {_COMPUTED}"
        note = (
            f"{label} rows sum to {total:g}% of revenue; the residual {remainder:g}% is "
            "carried as an unclassified remainder and is **not** forced into a segment. "
            f"{base} {_COMPUTED}"
        )
        return share_txt, note

    return (
        f"0% {_COMPUTED}",
        (
            f"{label} rows sum to {total:g}% of revenue and reconcile to the accounts "
            f"total with no unclassified remainder. {base} {_COMPUTED}"
        ),
    )


def _extract_segments_by_axis(
    corpus: str,
    *,
    universe: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    revenue_total = _revenue_total(corpus)
    universe = universe if isinstance(universe, dict) else {}
    primary = _population(universe.get("population_label"), default="accounts")
    out: list[dict[str, Any]] = []
    for axis in _AXES:
        rows, unclassified = _axis_candidate_rows(corpus, axis)
        share_txt, notes = _reconcile_notes(
            axis, rows, unclassified_pct=unclassified, revenue_total=revenue_total
        )
        population = "accounts" if axis == "contract_form" else primary
        if axis == "geography":
            population = "locations" if _is_filled(universe.get("locations_n")) else primary
        if axis == "contract_form" and _is_filled(universe.get("subscriptions_n")):
            population = "subscriptions"
        out.append({
            "axis": axis,
            "population": population,
            "rows": rows,
            "unclassified_share_pct": share_txt,
            "reconcile_notes": notes,
            "source": _DOC_CITE if rows else _NA,
        })
    return out


# ---------------------------------------------------------------------------
# heuristic — concentration
# ---------------------------------------------------------------------------


def _is_gross_profit_context(text: str, start: int, end: int) -> bool:
    """True where a share is measured on gross profit rather than on revenue."""
    window = (text or "")[max(0, start - 60) : end + 60]
    if not _GROSS_PROFIT_CUE.search(window):
        return False
    tail = (text or "")[end : end + 60]
    return not re.search(
        r"(?i)\b(revenue|turnover|sales|billings|income)\b", tail
    )


def _numeric_top_shares(corpus: str) -> tuple[dict[int, float], list[str]]:
    """Return ({n: revenue_share_pct}, evidence_snippets) from top-N statements."""
    text = corpus or ""
    found: dict[int, float] = {}
    evidence: list[str] = []

    def _record(n: Any, pct: Any, m: re.Match[str]) -> None:
        rank = _num(n)
        val = _num(pct)
        if rank is None or val is None:
            return
        idx = int(rank)
        if idx < 1 or idx > 50 or val < 0 or val > 100:
            return
        if _is_gross_profit_context(text, m.start(), m.end()):
            return
        if idx not in found:
            found[idx] = val
            snippet = _clean(m.group(0), 140)
            if snippet:
                evidence.append(snippet)

    for m in _TOP_N_SHARE.finditer(text):
        _record(m.group(1), m.group(2), m)
    for m in _SHARE_TOP_N.finditer(text):
        _record(m.group(2), m.group(1), m)
    for m in _TOP_1_SHARE.finditer(text):
        _record(1, m.group(1), m)
    for m in _SHARE_TOP_1.finditer(text):
        _record(1, m.group(1), m)
    return found, evidence[:4]


def _ranked_individual_shares(corpus: str) -> dict[int, float]:
    """Return {rank: revenue_share_pct} for individually ranked customer shares."""
    text = corpus or ""
    ranked: dict[int, float] = {}

    def _put(rank: int | None, pct: Any, m: re.Match[str]) -> None:
        val = _num(pct)
        if not rank or val is None or not (0 <= val <= 100):
            return
        if rank in ranked or not (1 <= rank <= 20):
            return
        if _is_gross_profit_context(text, m.start(), m.end()):
            return
        ranked[rank] = val

    for m in _TOP_1_SHARE.finditer(text):
        _put(1, m.group(1), m)
    for m in _ORDINAL_SHARE.finditer(text):
        _put(_ORDINAL_RANK.get(m.group(1).lower()), m.group(2), m)
    for m in _RANKED_SHARE.finditer(text):
        rank = _num(m.group(1))
        _put(int(rank) if rank is not None else None, m.group(2), m)
    return ranked


def _cumulative_from_ranked(ranked: dict[int, float], n: int) -> float | None:
    if not ranked:
        return None
    if not all(r in ranked for r in range(1, n + 1)):
        return None
    total = sum(ranked[r] for r in range(1, n + 1))
    return total if 0 <= total <= 100.5 else None


def _hhi_from_ranked(ranked: dict[int, float]) -> str:
    if len(ranked) < 3:
        return ""
    index = sum((v / 100.0) ** 2 for v in ranked.values()) * 10_000
    return (
        f"~{index:,.0f} (sum of squared parent shares × 10,000, computed on the "
        f"{len(ranked)} evidenced parent shares only — a floor, not a full-population "
        f"index) {_COMPUTED}"
    )


def _gross_profit_shares(corpus: str) -> dict[int, float]:
    """Top-N gross profit shares, read only from sentences that mention margin."""
    out: dict[int, float] = {}
    for sent in _sentences(corpus):
        if not _GROSS_PROFIT_CUE.search(sent):
            continue
        for m in _TOP_N_SHARE.finditer(sent):
            rank, val = _num(m.group(1)), _num(m.group(2))
            if rank is None or val is None:
                continue
            idx = int(rank)
            if 1 <= idx <= 50 and 0 <= val <= 100 and idx not in out:
                out[idx] = val
        for m in _TOP_1_SHARE.finditer(sent):
            val = _num(m.group(1))
            if val is not None and 0 <= val <= 100 and 1 not in out:
                out[1] = val
    return out


def _extract_concentration(
    corpus: str,
    *,
    ledger: dict[str, str] | None = None,
) -> dict[str, Any]:
    text = corpus or ""
    ledger = ledger if isinstance(ledger, dict) else {}
    ledger_status = str(ledger.get("status") or "missing")

    stated, evidence = _numeric_top_shares(text)
    ranked = _ranked_individual_shares(text)

    top_1 = stated.get(1)
    if top_1 is None:
        top_1 = ranked.get(1)
    top_5 = stated.get(5)
    top_10 = stated.get(10)

    derived_bits: list[str] = []
    if top_5 is None:
        derived = _cumulative_from_ranked(ranked, 5)
        if derived is not None:
            top_5 = derived
            derived_bits.append("top 5 summed from the five evidenced parent shares")
    if top_10 is None:
        derived = _cumulative_from_ranked(ranked, 10)
        if derived is not None:
            top_10 = derived
            derived_bits.append("top 10 summed from the ten evidenced parent shares")

    # Nearest-neighbour rungs (e.g. "top 3", "top 20") are reported, never relabelled.
    other_rungs = {
        n: v for n, v in stated.items() if n not in {1, 5, 10}
    }

    gp_stated = _gross_profit_shares(text)
    gp_top_1 = gp_stated.get(1)
    gp_top_5 = gp_stated.get(5)

    hhi_m = _HHI.search(text)
    if hhi_m:
        concentration_index = f"{_clean(hhi_m.group(0), 80)} {_DOC_CITE}"
    else:
        concentration_index = _hhi_from_ranked(ranked)

    parent_level = bool(_PARENT_AGGREGATION_CUE.search(text))
    calculable, notes = _concentration_calculable(
        top_1,
        top_5,
        top_10,
        ledger_status=ledger_status,
        population="parents" if parent_level or stated or ranked else "accounts",
        corpus=text,
        gross_profit_top_1=gp_top_1,
        gross_profit_top_5=gp_top_5,
    )

    extra: list[str] = []
    if evidence:
        extra.append("Stated in the packs: " + "; ".join(evidence) + f" {_DOC_CITE}")
    if derived_bits:
        extra.append("; ".join(derived_bits) + f" {_COMPUTED}")
    if other_rungs:
        extra.append(
            "Other rungs evidenced: "
            + ", ".join(f"top {n} {v:g}%" for n, v in sorted(other_rungs.items()))
            + f" — reported at the rung stated, never relabelled as top 1/5/10 {_DOC_CITE}"
        )
    if not parent_level and (stated or ranked):
        extra.append(
            "The packs do not confirm that related accounts are aggregated to parent "
            "level; the shares must be re-cut on parent ID before they are relied on"
        )
    if _QUALITATIVE_CONCENTRATION.search(text) and not calculable:
        extra.append(
            "The packs assert concentration in prose only; description is not a "
            "calculation, so no risk rating is carried from it"
        )
    calculation_notes = " ".join([notes] + extra).strip()

    info = ""
    if not calculable:
        info = _info_request(
            "customer-level revenue by parent for the audited period (parent ID, "
            "account IDs rolled up, revenue and gross profit per parent) so top 1 / "
            "top 5 / top 10 shares and a concentration index can be calculated"
        )

    return {
        "calculable": calculable,
        "population": "parents",
        "top_1_share_pct": _pct_or_none(top_1) if calculable else None,
        "top_5_share_pct": _pct_or_none(top_5) if calculable else None,
        "top_10_share_pct": _pct_or_none(top_10) if calculable else None,
        "concentration_index": (concentration_index or None) if calculable else None,
        "gross_profit_top_1_share_pct": _pct_or_none(gp_top_1) if calculable else None,
        "gross_profit_top_5_share_pct": _pct_or_none(gp_top_5) if calculable else None,
        "calculation_notes": calculation_notes,
        "information_request": info,
        "risk_rating": _risk_rating(
            calculable=calculable, top_1=top_1, top_5=top_5, top_10=top_10
        ),
        "source": _DOC_CITE if (stated or ranked or hhi_m) else _NA,
    }


# ---------------------------------------------------------------------------
# heuristic — largest contracts
# ---------------------------------------------------------------------------


def _is_counterparty_name(name: str) -> bool:
    """A contract-form or generic word is a label, not a counterparty."""
    if not name:
        return False
    stripped = re.sub(
        r"(?i)\s*\b(agreement|contract|MSA|framework|SOW|account|"
        r"arrangement|relationship)\b\s*",
        " ",
        name,
    ).strip()
    if not stripped:
        return False
    if _CONTRACT_FORM_VOCAB.fullmatch(stripped) or _SERVICE_VOCAB.fullmatch(stripped):
        return False
    return bool(_clean_row_name(stripped, max_chars=60))


def _contract_name(sent: str) -> str:
    for pattern in (_CONTRACT_NAMED, _CONTRACT_NAMED_ALT):
        for m in pattern.finditer(sent or ""):
            name = _clean_row_name(m.group(1), max_chars=60)
            if name and _is_counterparty_name(name):
                return name
    return ""


def _contract_share(sent: str, *, value: tuple[str, float] | None, total: tuple[str, float] | None) -> str:
    for m in _TOP_1_SHARE.finditer(sent):
        val = _num(m.group(1))
        if val is not None:
            return f"{_pct_text(val)} of revenue {_DOC_CITE}"
    m = re.search(
        r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:total\s+|group\s+)?"
        r"(?:revenue|turnover|sales|billings)",
        sent or "",
        re.IGNORECASE,
    )
    if m:
        return f"{_pct_text(m.group(1))} of revenue {_DOC_CITE}"
    if value and total and value[0] == total[0] and total[1] > 0:
        share = value[1] / total[1] * 100.0
        if 0 < share <= 100:
            return (
                f"{share:.1f}% of revenue (contract value ÷ revenue total in the "
                f"accounts, both in {total[0]}) {_COMPUTED}"
            )
    return _info_request(
        "contract value as a share of revenue in the accounts for the same period"
    )


def _extract_largest_contracts(corpus: str) -> list[dict[str, str]]:
    text = corpus or ""
    sents = _sentences(text)
    total = _revenue_total_value(text)
    scoped = [s for s in sents if _CONTRACT_CUE.search(s)]
    if not scoped:
        scoped = [
            s for s in sents
            if _TOP_1_SHARE.search(s) or _TERMINATION_CUE.search(s)
        ]

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for sent in scoped:
        money_m = _MONEY.search(sent)
        end_m = _END_DATE_CUE.search(sent)
        term_m = _TERMINATION_CUE.search(sent)
        # A bare percentage is not a contract — a segment-mix listing must not be
        # promoted into the contract table.
        if not (money_m or end_m or term_m or _TOP_1_SHARE.search(sent)):
            continue
        if (
            not (money_m or end_m or term_m)
            and _SEGMENT_GENERIC_CUE.search(sent)
            and len(re.findall(r"\d{1,3}(?:\.\d+)?\s*%", sent)) >= 2
        ):
            continue
        name = _contract_name(sent)
        key = (name or _clean(sent, 60)).lower()
        if key in seen:
            continue
        seen.add(key)

        value = (
            _money_value(money_m.group(1), money_m.group(2), money_m.group(3))
            if money_m
            else None
        )
        rows.append({
            "name": (
                _title_case(name)
                if name
                else _info_request(
                    "counterparty name for the largest contract (not named in the packs "
                    "opened — no name is inferred)"
                )
            ),
            "value": (
                f"{_clean(money_m.group(0).rstrip(' ,;.'), 60)} {_DOC_CITE}"
                if money_m
                else _info_request("annual contract value")
            ),
            "share_pct": _contract_share(sent, value=value, total=total),
            "end_date": (
                f"{_clean(end_m.group(0), 70)} {_DOC_CITE}"
                if end_m
                else _info_request("contract end date / expiry")
            ),
            "termination_rights": (
                f"{_clean(term_m.group(0), 110)} {_DOC_CITE}"
                if term_m
                else _info_request(
                    "termination rights — notice period, termination for convenience "
                    "and change-of-control provisions"
                )
            ),
            "source": _DOC_CITE,
        })
        if len(rows) >= 6:
            break

    if not rows:
        rows.append({
            "name": _info_request(
                "largest contracts by value, named from the contract register"
            ),
            "value": _info_request("annual contract value for each largest contract"),
            "share_pct": _info_request("each contract's share of revenue in the accounts"),
            "end_date": _info_request("contract end date / expiry for each"),
            "termination_rights": _info_request(
                "termination rights for each — notice period, termination for "
                "convenience, change of control"
            ),
            "source": _NA,
        })
    return rows[:6]


# ---------------------------------------------------------------------------
# heuristic — population discipline
# ---------------------------------------------------------------------------


def _population_discipline(
    *,
    universe: dict[str, str],
    axes: list[dict[str, Any]],
    concentration: dict[str, Any],
) -> dict[str, str]:
    primary = _population(universe.get("population_label"), default="accounts")
    used: dict[str, list[str]] = {}
    for axis in axes:
        if not isinstance(axis, dict):
            continue
        pop = _population(axis.get("population"), default=primary)
        used.setdefault(pop, []).append(
            _AXIS_LABEL.get(_axis_key(axis.get("axis")), str(axis.get("axis") or "axis"))
        )
    bits = [
        f"{pop}: {', '.join(labels)}"
        for pop, labels in sorted(used.items())
    ]
    conc_pop = _population(concentration.get("population"), default="parents")
    statement = (
        f"Primary population is **{primary}**. Concentration is computed on "
        f"**{conc_pop}** so that related accounts are counted once. "
        + (f"Axis populations — {'; '.join(bits)}. " if bits else "")
        + "Each table below states the population it counts; accounts, parents, "
        "locations and subscriptions are never mixed within one table, and a count on "
        f"one population is never presented as a count on another {_COMPUTED}"
    )

    caveat_bits: list[str] = []
    missing = [
        label
        for key, label in (
            ("accounts_n", "accounts"),
            ("parents_n", "parents"),
            ("locations_n", "locations"),
            ("subscriptions_n", "subscriptions"),
        )
        if not _is_filled(universe.get(key))
    ]
    if missing:
        caveat_bits.append(
            "not evidenced and therefore not counted: " + ", ".join(missing)
        )
    if len(used) > 1:
        caveat_bits.append(
            "axes are reported on different populations, so row counts are not "
            "additive across axes"
        )
    if not concentration.get("calculable"):
        caveat_bits.append(
            "concentration is unassessed, so no parent-level count is asserted and no "
            "risk rating is carried"
        )
    caveats = (
        "Caveats: " + "; ".join(caveat_bits) + "."
        if caveat_bits
        else (
            "All four populations are evidenced and each table states the population it "
            f"counts {_COMPUTED}"
        )
    )
    return {"statement": statement, "caveats": caveats}


# ---------------------------------------------------------------------------
# legacy dual-write (Ideal Customer Profile / decks)
# ---------------------------------------------------------------------------


def _legacy_segment_rows(legacy: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in (legacy or {}).get("segments") or []:
        if isinstance(raw, dict):
            rows.append(raw)
        elif hasattr(raw, "model_dump"):
            try:
                dumped = raw.model_dump()
                if isinstance(dumped, dict):
                    rows.append(dumped)
            except Exception:
                continue
    return rows


def _coerce_segment(raw: Any) -> dict[str, Any] | None:
    """Coerce to the legacy CustomerSegment shape decks expect."""
    if hasattr(raw, "model_dump"):
        try:
            raw = raw.model_dump()
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    name = _clean(raw.get("name"), 60)
    if not name or _PLACEHOLDER_NAME.match(name) or name.startswith("Information"):
        return None

    def _opt(key: str) -> str | None:
        val = raw.get(key)
        text = _clean(val, 80) if val is not None else ""
        return text or None

    return {
        "name": name,
        "share_pct": _num(raw.get("share_pct")),
        "avg_age": _opt("avg_age"),
        "use_case": _opt("use_case"),
        "key_driver": _opt("key_driver"),
    }


def _geo_mix_lines(axes: list[dict[str, Any]], legacy: dict[str, Any]) -> list[Any]:
    """Preserve the legacy geo_mix shape (list of 'Region: N% revenue share' strings)."""
    raw_legacy = legacy.get("geo_mix") or []
    out: list[Any] = []
    for item in raw_legacy:
        if isinstance(item, str) and item.strip():
            out.append(_clean(item, 120))
        elif isinstance(item, dict):
            region = _clean(item.get("region") or item.get("name"), 60)
            pct = _pct_text(item.get("share_pct"))
            if region and pct:
                out.append(f"{region}: {pct} revenue share")
            elif region:
                out.append(region)
    if out:
        return out[:6]

    geo_axis = next(
        (a for a in axes if isinstance(a, dict) and _axis_key(a.get("axis")) == "geography"),
        None,
    )
    for row in (geo_axis or {}).get("rows") or []:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("name"), 60)
        pct = _pct_text(row.get("share_pct"))
        if not name:
            continue
        out.append(f"{name}: {pct} revenue share" if pct else name)
        if len(out) >= 6:
            break
    return out


def _derive_legacy_segments(
    axes: list[dict[str, Any]],
    legacy: dict[str, Any],
) -> list[dict[str, Any]]:
    seeded: list[dict[str, Any]] = []
    for raw in _legacy_segment_rows(legacy):
        row = _coerce_segment(raw)
        if row:
            seeded.append(row)
    if seeded:
        return seeded[:8]

    for axis_key in ("customer_type", "service", "contract_form", "geography"):
        axis = next(
            (a for a in axes if isinstance(a, dict) and _axis_key(a.get("axis")) == axis_key),
            None,
        )
        rows = (axis or {}).get("rows") or []
        derived: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            coerced = _coerce_segment({
                "name": row.get("name"),
                "share_pct": _num(row.get("share_pct")),
                "use_case": (
                    _AXIS_LABEL.get(axis_key, axis_key) + " axis"
                ),
                "key_driver": (
                    _clean(row.get("customer_count"), 80)
                    if _is_filled(row.get("customer_count"))
                    else None
                ),
            })
            if coerced:
                derived.append(coerced)
        if derived:
            return derived[:8]
    return []


def _derive_icp_notes(
    corpus: str,
    legacy: dict[str, Any],
    *,
    concentration: dict[str, Any],
    axes: list[dict[str, Any]],
    ledger: dict[str, str],
) -> list[str]:
    calculable = bool(concentration.get("calculable"))
    notes: list[str] = []

    if calculable:
        bits = [
            f"top {label} {value}"
            for label, value in (
                ("1", concentration.get("top_1_share_pct")),
                ("5", concentration.get("top_5_share_pct")),
                ("10", concentration.get("top_10_share_pct")),
            )
            if value
        ]
        if bits:
            notes.append(
                "Parent-level revenue concentration calculated: "
                + ", ".join(bits)
                + f" {_COMPUTED}"
            )
    else:
        notes.append(
            "Concentration is unassessed — the billing ledger at parent level was not "
            "opened, so no top 1 / top 5 / top 10 share is calculated and any risk "
            "rating is withheld. An empty concentration table is not high risk."
        )

    for axis in axes:
        if not isinstance(axis, dict) or not axis.get("rows"):
            continue
        label = _AXIS_LABEL.get(_axis_key(axis.get("axis")), "Segment")
        top = max(
            (r for r in axis["rows"] if isinstance(r, dict)),
            key=lambda r: _num(r.get("share_pct")) or 0.0,
            default=None,
        )
        if top:
            notes.append(
                f"{label}: largest row is {_clean(top.get('name'), 50)} at "
                f"{_clean(top.get('share_pct'), 20)} of revenue, counted on "
                f"{_population(axis.get('population'))} {_DOC_CITE}"
            )
        if len(notes) >= 4:
            break

    if str(ledger.get("status")) != "resolved" and len(notes) < 5:
        notes.append(_clean(ledger.get("notes"), 220))

    if len(notes) < 5:
        for sent in _pick_sentences(
            _sentences(corpus),
            keywords=(
                "customer", "segment", "concentration", "contract", "revenue",
                "retention", "ledger",
            ),
            limit=5,
        ):
            notes.append(_soften_concentration(_clean(sent, 200), calculable=calculable))
            if len(notes) >= 5:
                break

    cleaned = list(
        dict.fromkeys([n for n in notes if isinstance(n, str) and n.strip()])
    )
    if cleaned:
        return cleaned[:5]
    return [
        _soften_concentration(x, calculable=calculable)
        for x in (legacy.get("icp_notes") or [])
        if isinstance(x, str) and x.strip()
    ][:5]


def _legacy_fields(
    corpus: str,
    legacy: dict[str, Any] | None,
    *,
    axes: list[dict[str, Any]],
    concentration: dict[str, Any],
    ledger: dict[str, str],
) -> dict[str, list[Any]]:
    legacy = legacy if isinstance(legacy, dict) else {}
    return {
        "segments": _derive_legacy_segments(axes, legacy),
        "geo_mix": _geo_mix_lines(axes, legacy),
        "icp_notes": _derive_icp_notes(
            corpus,
            legacy,
            concentration=concentration,
            axes=axes,
            ledger=ledger,
        ),
    }


# ---------------------------------------------------------------------------
# quality / reliance
# ---------------------------------------------------------------------------


def _axes_reconciled(axes: list[dict[str, Any]]) -> bool:
    for axis in axes:
        if not isinstance(axis, dict) or not axis.get("rows"):
            continue
        total = _sum_shares(axis["rows"])
        if total is None:
            continue
        if _is_filled(axis.get("unclassified_share_pct")) or total >= 60:
            return True
    return False


def _contracts_named(contracts: list[dict[str, Any]]) -> int:
    return sum(
        1
        for c in contracts
        if isinstance(c, dict)
        and _is_filled(c.get("name"))
        and not str(c.get("name") or "").startswith("Information")
    )


def _quality_reliance(
    *,
    calculable: bool,
    ledger_status: str,
    axis_row_count: int,
    axes_reconciled: bool,
    contracts_named: int,
    universe_filled: int,
) -> tuple[str, str, str]:
    evidence = (
        f"{axis_row_count} segment row(s) across service / customer type / geography / "
        f"contract form; segment revenue "
        f"{'reconciled to the accounts with the remainder shown' if axes_reconciled else 'not reconciled to the accounts'}; "
        f"{contracts_named} contract(s) named with value, share, end date and "
        f"termination rights; {universe_filled} of 4 customer populations evidenced; "
        f"ledger {ledger_status}."
    )
    if calculable and (axes_reconciled or contracts_named):
        return (
            "PASS",
            "READY",
            (
                "Concentration is calculated from parent-level revenue shares and the "
                f"segmentation is evidenced. {evidence}"
            ),
        )
    if calculable:
        return (
            "PASS",
            "LIMITED",
            (
                "Concentration is calculated, but segment revenue is neither reconciled "
                f"to the accounts nor supported by named contracts. {evidence}"
            ),
        )
    if axis_row_count or contracts_named or ledger_status == "partial" or universe_filled:
        return (
            "PASS",
            "LIMITED",
            (
                "Concentration is unassessed — the parent-level ledger was not opened, "
                "so no top 1 / top 5 / top 10 share is calculated and any risk rating "
                "is withheld. An empty concentration table is not a high-risk finding. "
                f"{evidence}"
            ),
        )
    return (
        "PASS",
        "BLOCKED",
        (
            "No billing ledger or investor workbook was resolved and no segment "
            "evidence was found in the packs opened, so neither segmentation nor "
            "concentration can be assessed. Concentration is unassessed and any risk "
            f"rating is withheld — an empty table is not high risk. {evidence}"
        ),
    )


# ---------------------------------------------------------------------------
# heuristic composer
# ---------------------------------------------------------------------------


def _heuristic_customer_segmentation_spec(
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

    extra_bits: list[str] = []
    for key in ("icp_notes", "geo_mix"):
        for item in (legacy.get(key) or [])[:8]:
            if isinstance(item, str) and item.strip():
                extra_bits.append(item.strip())
            elif isinstance(item, dict):
                region = _clean(item.get("region") or item.get("name"), 60)
                pct = _pct_text(item.get("share_pct"))
                if region:
                    extra_bits.append(f"{region}: {pct} revenue share" if pct else region)
    for raw in _legacy_segment_rows(legacy)[:8]:
        name = _clean(raw.get("name"), 60)
        pct = raw.get("share_pct")
        if name:
            bits = [name]
            if pct is not None:
                bits.append(f"{_pct_text(pct)} of the customer mix")
            extra_bits.append(" — ".join(bits))
    if geography and str(geography).strip():
        extra_bits.append(f"Geography focus in the mandate: {_clean(geography, 60)}")
    corpus_full = (corpus or "") + ("\n" + "\n".join(extra_bits) if extra_bits else "")

    ledger = _extract_ledger_resolution(corpus_full)
    universe = _extract_customer_universe(corpus_full, ledger_status=ledger["status"])
    axes = _extract_segments_by_axis(corpus_full, universe=universe)
    concentration = _extract_concentration(corpus_full, ledger=ledger)
    contracts = _extract_largest_contracts(corpus_full)
    discipline = _population_discipline(
        universe=universe, axes=axes, concentration=concentration
    )
    legacy_fields = _legacy_fields(
        corpus_full,
        legacy,
        axes=axes,
        concentration=concentration,
        ledger=ledger,
    )

    calculable = bool(concentration.get("calculable"))
    axis_row_count = sum(
        len(a.get("rows") or []) for a in axes if isinstance(a, dict)
    )
    reconciled = _axes_reconciled(axes)
    named = _contracts_named(contracts)
    universe_filled = sum(
        1
        for key in ("accounts_n", "parents_n", "locations_n", "subscriptions_n")
        if _is_filled(universe.get(key))
    )
    quality, reliance, rationale = _quality_reliance(
        calculable=calculable,
        ledger_status=ledger["status"],
        axis_row_count=axis_row_count,
        axes_reconciled=reconciled,
        contracts_named=named,
        universe_filled=universe_filled,
    )

    if calculable:
        conc_txt = "concentration calculated at parent level (" + ", ".join(
            f"top {label} {value}"
            for label, value in (
                ("1", concentration.get("top_1_share_pct")),
                ("5", concentration.get("top_5_share_pct")),
                ("10", concentration.get("top_10_share_pct")),
            )
            if value
        ) + ")"
    else:
        conc_txt = (
            "concentration unassessed — the parent-level ledger is requested and any "
            "risk rating is withheld"
        )
    insight = _soften_concentration(
        (
            f"Customer Segmentation for {company}: ledger {ledger['status']}; "
            f"{universe_filled} of 4 customer populations evidenced; "
            f"{axis_row_count} segment row(s) across service, customer type, geography "
            f"and contract form"
            + (
                " reconciled to the accounts with any unclassified remainder shown"
                if reconciled
                else " not yet reconciled to the accounts"
            )
            + f"; {conc_txt}; {named} largest contract(s) named with value, share, end "
            "date and termination rights. Populations are stated per table and never "
            "mixed."
        ),
        calculable=calculable,
    )

    return {
        "insight_snapshot": insight,
        "ledger_resolution": ledger,
        "customer_universe": universe,
        "segments_by_axis": axes,
        "concentration": concentration,
        "largest_contracts": contracts,
        "population_discipline": discipline,
        "segments": legacy_fields["segments"],
        "geo_mix": legacy_fields["geo_mix"],
        "icp_notes": legacy_fields["icp_notes"],
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": list(sources or [])[:16],
        "composer": "heuristic_v1",
        "empty": (
            not calculable
            and axis_row_count == 0
            and named == 0
            and universe_filled == 0
            and not legacy_fields["segments"]
        ),
    }


# ---------------------------------------------------------------------------
# LLM composer
# ---------------------------------------------------------------------------


def _llm_customer_segmentation_spec(
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
        system = compose_system(
            "customer_segmentation",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
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
        "ledger_resolution: {status (resolved|partial|missing), source_doc, grain, "
        "notes, information_request, source},\n"
        "customer_universe: {accounts_n, parents_n, locations_n, subscriptions_n, "
        "population_label, source},\n"
        "segments_by_axis: [{axis (service|customer_type|geography|contract_form), "
        "population (accounts|parents|locations|subscriptions), "
        "rows: [{name, revenue, share_pct, customer_count, gp_share_pct}], "
        "unclassified_share_pct, reconcile_notes, source}],\n"
        "concentration: {calculable (bool), population (parents), top_1_share_pct, "
        "top_5_share_pct, top_10_share_pct, concentration_index, "
        "gross_profit_top_1_share_pct, gross_profit_top_5_share_pct, "
        "calculation_notes, information_request, risk_rating, source},\n"
        "largest_contracts: [{name, value, share_pct, end_date, termination_rights, "
        "source}],\n"
        "population_discipline: {statement, caveats},\n"
        "segments: [{name, share_pct, avg_age, use_case, key_driver}] — legacy ICP "
        "shape for decks, names only from the evidence,\n"
        "geo_mix: [string] in the form 'Region: 34% revenue share',\n"
        "icp_notes: [string],\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n\n"
        "Rules:\n"
        "Resolve the billing ledger / investor workbook pointers first and build a "
        "customer-level view with account, parent and location identifiers.\n"
        "Concentration must be calculated from parent-level revenue shares — top 1, "
        "top 5 and top 10 — so that related accounts are counted together. "
        "Concentration must be CALCULATED, never described.\n"
        "If the billing ledger is missing, concentration is unassessed — set "
        "calculable false, leave every share null, request the ledger and withhold the "
        "risk rating (risk_rating null or 'withheld'). An empty table is not high "
        "risk: never infer high concentration risk from an empty or missing table.\n"
        "Add a concentration index (HHI or similar) only if the data support it. "
        "Repeat the top 1 / top 5 calculation for gross profit only if customer-level "
        "margin data exist.\n"
        "Reconcile segment revenue to the revenue total in the accounts and show the "
        "unclassified remainder — never force revenue into a segment.\n"
        "State which population every count refers to: accounts, parents, locations or "
        "subscriptions. Do NOT mix populations in one table.\n"
        "Name the largest contracts with value, share of revenue, end date and "
        "termination rights. Never invent customer or counterparty names — if a name "
        "is not in the evidence, raise a named information request instead.\n"
        "Do NOT recommend invest or pass. Do NOT include recommendation, confidence or "
        "investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# normalise
# ---------------------------------------------------------------------------


def _normalise_ledger(llm: dict[str, Any], corpus: str) -> dict[str, Any]:
    ledger = llm.get("ledger_resolution")
    if not isinstance(ledger, dict):
        return _extract_ledger_resolution(corpus)
    status = str(ledger.get("status") or "").strip().lower()
    if status not in {"resolved", "partial", "missing"}:
        status = "resolved" if _is_filled(ledger.get("source_doc")) else "missing"
    if status == "resolved" and not _is_filled(ledger.get("source_doc")):
        status = "partial"
    ledger["status"] = status
    for key, label in (
        ("source_doc", "name and location of the billing ledger / investor workbook"),
        (
            "grain",
            "customer-level grain of the ledger — whether account, parent and location "
            "identifiers are present",
        ),
    ):
        if not str(ledger.get(key) or "").strip():
            ledger[key] = _info_request(label)
    if not str(ledger.get("notes") or "").strip():
        ledger["notes"] = (
            _extract_ledger_resolution(corpus)["notes"]
            if status != "resolved"
            else f"Ledger opened as the customer-level source {_DOC_CITE}"
        )
    if status == "resolved":
        ledger["information_request"] = str(ledger.get("information_request") or "")
    elif not _is_filled(ledger.get("information_request")):
        ledger["information_request"] = _info_request(
            "the billing ledger or investor workbook at customer level for the audited "
            "period, with account ID, parent ID, location ID, revenue and — where held "
            "— gross profit per row"
        )
    ledger.setdefault("source", _DOC_CITE)
    return ledger


def _normalise_universe(llm: dict[str, Any], corpus: str, *, ledger_status: str) -> dict[str, Any]:
    universe = llm.get("customer_universe")
    if not isinstance(universe, dict):
        return _extract_customer_universe(corpus, ledger_status=ledger_status)
    for key, label in (
        ("accounts_n", "number of customer accounts in the ledger"),
        ("parents_n", "number of parent groups once related accounts are rolled up"),
        ("locations_n", "number of customer locations / sites served"),
        ("subscriptions_n", "number of live subscriptions / contract lines"),
    ):
        raw = universe.get(key)
        if not str(raw or "").strip():
            universe[key] = _info_request(label)
        elif _is_filled(raw):
            value = _count_text(raw, context=str(raw))
            universe[key] = f"{value} {_DOC_CITE}" if value else _info_request(label)
    primary = _population(universe.get("population_label"), default="")
    if not primary:
        primary = (
            "parents" if _is_filled(universe.get("parents_n"))
            else "accounts" if _is_filled(universe.get("accounts_n"))
            else "subscriptions" if _is_filled(universe.get("subscriptions_n"))
            else "locations" if _is_filled(universe.get("locations_n"))
            else "accounts"
        )
    filled = sum(
        1
        for key in ("accounts_n", "parents_n", "locations_n", "subscriptions_n")
        if _is_filled(universe.get(key))
    )
    label_text = str(universe.get("population_label") or "").strip()
    if not label_text or primary not in label_text.lower():
        universe["population_label"] = (
            f"Primary population for revenue and segment counts: **{primary}**. "
            f"{filled} of 4 populations are evidenced; the remainder are named as "
            f"information requests rather than inferred from each other {_COMPUTED}"
        )
    universe.setdefault("source", _DOC_CITE if filled else _NA)
    return universe


def _normalise_axes(
    llm: dict[str, Any],
    corpus: str,
    *,
    universe: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_axes = llm.get("segments_by_axis")
    revenue_total = _revenue_total(corpus)
    primary = _population(universe.get("population_label"), default="accounts")
    cleaned: list[dict[str, Any]] = []
    seen_axes: set[str] = set()

    for raw in raw_axes or []:
        if not isinstance(raw, dict):
            continue
        axis = _axis_key(raw.get("axis"))
        if axis in seen_axes:
            continue
        rows: list[dict[str, Any]] = []
        declared: float | None = None
        for row in raw.get("rows") or []:
            if not isinstance(row, dict):
                continue
            name = _clean_row_name(row.get("name"), max_chars=60)
            if not name:
                continue
            pct = _num(row.get("share_pct"))
            if pct is not None and not (0 <= pct <= 100):
                pct = None
            if _UNCLASSIFIED_CUE.fullmatch(name.lower()) and pct is not None:
                declared = pct
                continue
            out_row: dict[str, Any] = {
                "name": _title_case(name),
                "revenue": (
                    _clean(row.get("revenue"), 120)
                    if _is_filled(row.get("revenue"))
                    else (
                        f"{_pct_text(pct)} of revenue {_DOC_CITE}"
                        if pct is not None
                        else _info_request("segment revenue in the accounts")
                    )
                ),
                "share_pct": _pct_text(pct) if pct is not None else _info_request(
                    "segment share of revenue"
                ),
                "customer_count": (
                    _clean(row.get("customer_count"), 80)
                    if _is_filled(row.get("customer_count"))
                    else _info_request(
                        "customer count for this segment, on a stated population"
                    )
                ),
            }
            gp = _num(row.get("gp_share_pct"))
            if gp is not None and 0 <= gp <= 100:
                out_row["gp_share_pct"] = _pct_text(gp)
            rows.append(out_row)
            if len(rows) >= 8:
                break

        if declared is None:
            declared = _num(raw.get("unclassified_share_pct"))
            if declared is not None and not (0 <= declared <= 100):
                declared = None
        share_txt, notes = _reconcile_notes(
            axis, rows, unclassified_pct=declared, revenue_total=revenue_total
        )
        population = _population(raw.get("population"), default=primary)
        cleaned.append({
            "axis": axis,
            "population": population,
            "rows": rows,
            "unclassified_share_pct": (
                _clean(raw.get("unclassified_share_pct"), 80)
                if _is_filled(raw.get("unclassified_share_pct")) and declared is not None
                else share_txt
            ),
            "reconcile_notes": (
                f"{_clean(raw.get('reconcile_notes'), 260)} {notes}"
                if _is_filled(raw.get("reconcile_notes"))
                else notes
            ),
            "source": raw.get("source") or (_DOC_CITE if rows else _NA),
        })
        seen_axes.add(axis)

    if not cleaned:
        return _extract_segments_by_axis(corpus, universe=universe)

    heuristic = {
        _axis_key(a.get("axis")): a
        for a in _extract_segments_by_axis(corpus, universe=universe)
        if isinstance(a, dict)
    }
    for axis in _AXES:
        if axis not in seen_axes and axis in heuristic:
            cleaned.append(heuristic[axis])
    order = {axis: i for i, axis in enumerate(_AXES)}
    cleaned.sort(key=lambda a: order.get(_axis_key(a.get("axis")), 9))
    return cleaned


def _normalise_concentration(
    llm: dict[str, Any],
    corpus: str,
    *,
    ledger_status: str,
) -> dict[str, Any]:
    conc = llm.get("concentration")
    heuristic = _extract_concentration(corpus, ledger={"status": ledger_status})
    if not isinstance(conc, dict):
        return heuristic

    top_1 = _num(conc.get("top_1_share_pct"))
    top_5 = _num(conc.get("top_5_share_pct"))
    top_10 = _num(conc.get("top_10_share_pct"))
    gp_1 = _num(conc.get("gross_profit_top_1_share_pct"))
    gp_5 = _num(conc.get("gross_profit_top_5_share_pct"))

    # A model claim is only adopted where the arithmetic itself holds up.
    calculable, notes = _concentration_calculable(
        top_1,
        top_5,
        top_10,
        ledger_status=ledger_status,
        population=conc.get("population") or "parents",
        corpus=corpus,
        gross_profit_top_1=gp_1,
        gross_profit_top_5=gp_5,
    )
    claimed = bool(conc.get("calculable"))
    calculable = bool(calculable and claimed)
    if not claimed and (top_1 is not None or top_5 is not None or top_10 is not None):
        # Shares were supplied without the flag; trust the arithmetic check.
        recheck, notes = _concentration_calculable(
            top_1,
            top_5,
            top_10,
            ledger_status=ledger_status,
            population=conc.get("population") or "parents",
            corpus=corpus,
            gross_profit_top_1=gp_1,
            gross_profit_top_5=gp_5,
        )
        calculable = bool(recheck)

    if not calculable and heuristic.get("calculable"):
        return heuristic

    conc["calculable"] = calculable
    conc["population"] = "parents"
    if calculable:
        conc["top_1_share_pct"] = _pct_or_none(top_1)
        conc["top_5_share_pct"] = _pct_or_none(top_5)
        conc["top_10_share_pct"] = _pct_or_none(top_10)
        conc["gross_profit_top_1_share_pct"] = _pct_or_none(gp_1)
        conc["gross_profit_top_5_share_pct"] = _pct_or_none(gp_5)
        index = conc.get("concentration_index")
        conc["concentration_index"] = _clean(index, 120) if _is_filled(index) else None
        conc["information_request"] = str(conc.get("information_request") or "")
        conc["risk_rating"] = _risk_rating(
            calculable=True, top_1=top_1, top_5=top_5, top_10=top_10
        )
    else:
        for key in (
            "top_1_share_pct",
            "top_5_share_pct",
            "top_10_share_pct",
            "concentration_index",
            "gross_profit_top_1_share_pct",
            "gross_profit_top_5_share_pct",
        ):
            conc[key] = None
        conc["risk_rating"] = _WITHHELD
        if not _is_filled(conc.get("information_request")):
            conc["information_request"] = heuristic["information_request"] or _info_request(
                "customer-level revenue by parent for the audited period so top 1 / "
                "top 5 / top 10 shares can be calculated"
            )

    existing = str(conc.get("calculation_notes") or "").strip()
    if not existing:
        conc["calculation_notes"] = notes
    elif not calculable and "not calculable" not in existing.lower():
        conc["calculation_notes"] = (
            _soften_concentration(_clean(existing, 300), calculable=False) + " " + notes
        )
    else:
        conc["calculation_notes"] = _clean(existing, 400)
    conc.setdefault("source", _DOC_CITE if calculable else _NA)
    return conc


def _normalise_contracts(llm: dict[str, Any], corpus: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for raw in llm.get("largest_contracts") or []:
        if not isinstance(raw, dict):
            continue
        name = _clean_row_name(raw.get("name"), max_chars=60)
        row = dict(raw)
        row["name"] = (
            _title_case(name)
            if name
            else _info_request(
                "counterparty name for this contract (no name is inferred)"
            )
        )
        for key, label in (
            ("value", "annual contract value"),
            ("share_pct", "contract share of revenue in the accounts"),
            ("end_date", "contract end date / expiry"),
            (
                "termination_rights",
                "termination rights — notice period, termination for convenience and "
                "change-of-control provisions",
            ),
        ):
            if not str(row.get(key) or "").strip():
                row[key] = _info_request(label)
        if _is_filled(row.get("share_pct")):
            pct = _num(row.get("share_pct"))
            if pct is not None and 0 <= pct <= 100:
                row["share_pct"] = f"{_pct_text(pct)} of revenue {_DOC_CITE}"
        row.setdefault("source", _DOC_CITE)
        cleaned.append(row)
        if len(cleaned) >= 6:
            break
    if not cleaned:
        return _extract_largest_contracts(corpus)
    return cleaned


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    ledger = _normalise_ledger(llm, corpus)
    llm["ledger_resolution"] = ledger
    ledger_status = str(ledger.get("status") or "missing")

    universe = _normalise_universe(llm, corpus, ledger_status=ledger_status)
    llm["customer_universe"] = universe

    axes = _normalise_axes(llm, corpus, universe=universe)
    llm["segments_by_axis"] = axes

    concentration = _normalise_concentration(llm, corpus, ledger_status=ledger_status)
    llm["concentration"] = concentration
    calculable = bool(concentration.get("calculable"))
    if not calculable and concentration.get("risk_rating") not in (None, _WITHHELD):
        concentration["risk_rating"] = _WITHHELD

    contracts = _normalise_contracts(llm, corpus)
    llm["largest_contracts"] = contracts

    discipline = llm.get("population_discipline")
    heuristic_discipline = _population_discipline(
        universe=universe, axes=axes, concentration=concentration
    )
    if not isinstance(discipline, dict):
        discipline = heuristic_discipline
    else:
        for key in ("statement", "caveats"):
            if not str(discipline.get(key) or "").strip():
                discipline[key] = heuristic_discipline[key]
            else:
                discipline[key] = _soften_concentration(
                    _clean(discipline[key], 420), calculable=calculable
                )
    llm["population_discipline"] = discipline

    # --- legacy dual-write -------------------------------------------------
    heur_legacy = _legacy_fields(
        corpus,
        legacy,
        axes=axes,
        concentration=concentration,
        ledger=ledger,
    )
    segments: list[dict[str, Any]] = []
    for raw in llm.get("segments") or []:
        row = _coerce_segment(raw)
        if row:
            segments.append(row)
    llm["segments"] = segments[:8] or heur_legacy["segments"]

    geo_raw = llm.get("geo_mix")
    geo_out: list[Any] = []
    for item in geo_raw or []:
        if isinstance(item, str) and item.strip():
            geo_out.append(_clean(item, 120))
        elif isinstance(item, dict):
            region = _clean(item.get("region") or item.get("name"), 60)
            pct = _pct_text(item.get("share_pct"))
            if region and pct:
                geo_out.append(f"{region}: {pct} revenue share")
            elif region:
                geo_out.append(region)
    llm["geo_mix"] = geo_out[:6] or heur_legacy["geo_mix"]

    notes_raw = llm.get("icp_notes")
    if isinstance(notes_raw, list) and notes_raw:
        llm["icp_notes"] = [
            _soften_concentration(_clean(x, 240), calculable=calculable)
            for x in notes_raw
            if isinstance(x, str) and x.strip()
        ][:5]
    else:
        llm["icp_notes"] = heur_legacy["icp_notes"]

    # --- verdicts / housekeeping ------------------------------------------
    axis_row_count = sum(len(a.get("rows") or []) for a in axes if isinstance(a, dict))
    named = _contracts_named(contracts)
    universe_filled = sum(
        1
        for key in ("accounts_n", "parents_n", "locations_n", "subscriptions_n")
        if _is_filled(universe.get(key))
    )
    quality, reliance, rationale = _quality_reliance(
        calculable=calculable,
        ledger_status=ledger_status,
        axis_row_count=axis_row_count,
        axes_reconciled=_axes_reconciled(axes),
        contracts_named=named,
        universe_filled=universe_filled,
    )
    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else quality
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else reliance
    if not str(llm.get("quality_reliance_rationale") or "").strip():
        llm["quality_reliance_rationale"] = rationale
    else:
        llm["quality_reliance_rationale"] = _soften_concentration(
            _clean(llm["quality_reliance_rationale"], 420), calculable=calculable
        )
    if not calculable and llm["reliance_verdict"] == "READY":
        llm["reliance_verdict"] = "LIMITED"
        llm["quality_reliance_rationale"] = (
            "Concentration is unassessed — the parent-level ledger was not opened, so "
            "any risk rating is withheld and an empty table is not treated as high "
            "risk; reliance is therefore limited. "
            + _clean(llm.get("quality_reliance_rationale"), 300)
        )
    if ledger_status == "missing" and axis_row_count == 0 and named == 0:
        llm["reliance_verdict"] = "BLOCKED"

    for dead in (
        "recommendation",
        "confidence",
        "investment_verdict",
        "key_conditions",
        "verdict",
    ):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_concentration(
        llm.get("insight_snapshot") or "", calculable=calculable
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = (
        not calculable
        and axis_row_count == 0
        and named == 0
        and universe_filled == 0
        and not llm["segments"]
    )
    return llm


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def build_customer_segmentation_spec(
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
    geography = vars_.get("geography")
    sector = vars_.get("sector")

    if corpus is None:
        gathered_corpus, gathered_sources = gather_customer_segmentation_corpus(deal, idx)
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
        llm = _llm_customer_segmentation_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=sector,
            geography=geography,
            materiality=vars_.get("materiality"),
        )
        if llm:
            return _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
            )

    return _heuristic_customer_segmentation_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        sector=sector,
        geography=geography,
        legacy_spec=legacy_spec,
    )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def _render_axis(axis: dict[str, Any]) -> str:
    axis_key = _axis_key(axis.get("axis"))
    label = _AXIS_LABEL.get(axis_key, axis_key)
    population = _population(axis.get("population"))
    rows = axis.get("rows") if isinstance(axis.get("rows"), list) else []
    parts: list[str] = [f"### {label} — counted on **{population}**\n\n"]
    if rows:
        show_gp = any(
            isinstance(r, dict) and str(r.get("gp_share_pct") or "").strip() for r in rows
        )
        headers = ["Segment", "Revenue", "Share of revenue", f"Customers ({population})"]
        if show_gp:
            headers.append("GP share")
        body: list[list[str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            cells = [
                _clean(row.get("name"), 60),
                _clean(row.get("revenue"), 90),
                _clean(row.get("share_pct"), 40),
                _clean(row.get("customer_count"), 90),
            ]
            if show_gp:
                cells.append(_clean(row.get("gp_share_pct"), 30) or "—")
            body.append(cells)
        parts.append(_table(headers, body))
    else:
        parts.append(
            f"No {label.lower()} split was evidenced in the packs opened. Nothing is "
            "inferred and no remainder is implied.\n\n"
        )
    parts.append(
        f"- **Unclassified remainder:** {_clean(axis.get('unclassified_share_pct'), 120)}\n"
    )
    parts.append(
        f"- **Reconciliation to the accounts:** {_clean(axis.get('reconcile_notes'), 420)}\n"
    )
    parts.append(f"- **Source:** {_clean(axis.get('source') or _NA, 60)}\n\n")
    return "".join(parts)


def render_customer_segmentation_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    ledger = (
        spec.get("ledger_resolution")
        if isinstance(spec.get("ledger_resolution"), dict)
        else {}
    )
    universe = (
        spec.get("customer_universe")
        if isinstance(spec.get("customer_universe"), dict)
        else {}
    )
    axes = (
        spec.get("segments_by_axis")
        if isinstance(spec.get("segments_by_axis"), list)
        else []
    )
    concentration = (
        spec.get("concentration") if isinstance(spec.get("concentration"), dict) else {}
    )
    contracts = (
        spec.get("largest_contracts")
        if isinstance(spec.get("largest_contracts"), list)
        else []
    )
    discipline = (
        spec.get("population_discipline")
        if isinstance(spec.get("population_discipline"), dict)
        else {}
    )
    srcs = sources or spec.get("primary_sources") or spec.get("sources") or []
    calculable = bool(concentration.get("calculable"))
    primary_pop = _population(universe.get("population_label"), default="accounts")

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # --- 1 ----------------------------------------------------------------
    parts.append("## 1. Ledger & Customer Universe\n\n")
    parts.append(
        "Pointers to the billing ledger or investor workbook are resolved first, so the "
        "customer-level view carries account, parent and location identifiers. Every "
        "count below states the population it refers to.\n\n"
    )
    parts.append(_table(
        ["Item", "Value"],
        [
            ["Ledger status", _clean(ledger.get("status") or "missing", 30)],
            ["Source document", _clean(ledger.get("source_doc"), 200)],
            ["Customer-level grain", _clean(ledger.get("grain"), 260)],
            ["Notes", _clean(ledger.get("notes"), 360)],
            ["Source", _clean(ledger.get("source") or _NA, 60)],
        ],
    ))
    if _is_filled(ledger.get("information_request")):
        parts.append(f"**{_clean(ledger.get('information_request'), 320)}**\n\n")
    parts.append(_table(
        ["Population", "Count"],
        [
            ["Accounts", _clean(universe.get("accounts_n"), 140)],
            ["Parents", _clean(universe.get("parents_n"), 140)],
            ["Locations", _clean(universe.get("locations_n"), 140)],
            ["Subscriptions", _clean(universe.get("subscriptions_n"), 140)],
            ["Primary population", _clean(universe.get("population_label"), 300)],
            ["Source", _clean(universe.get("source") or _NA, 60)],
        ],
    ))
    parts.append("---\n\n")

    # --- 2 ----------------------------------------------------------------
    parts.append("## 2. Segmentation by Axis (Reconciled)\n\n")
    parts.append(
        "Revenue is segmented by service, customer type, geography and contract form. "
        "Each axis is reconciled to the revenue total in the accounts and any "
        "unclassified remainder is shown rather than forced into a segment. Each table "
        "counts a single population.\n\n"
    )
    if axes:
        for axis in axes:
            if isinstance(axis, dict):
                parts.append(_render_axis(axis))
    else:
        parts.append(
            "No segmentation axis was evidenced in the packs opened. The segment split "
            "is requested rather than assumed.\n\n"
        )
    parts.append("---\n\n")

    # --- 3 ----------------------------------------------------------------
    parts.append("## 3. Concentration (Parent-Level, Calculated)\n\n")
    parts.append(
        "Concentration is **calculated** from revenue aggregated to **parent** level so "
        "that related accounts are counted together — it is never described. Shares "
        "below are top 1 / top 5 / top 10 of revenue on parents.\n\n"
    )
    if calculable:
        rows = [
            ["Population", _population(concentration.get("population"), default="parents")],
            ["Top 1 share of revenue", _clean(concentration.get("top_1_share_pct") or _NA, 40)],
            ["Top 5 share of revenue", _clean(concentration.get("top_5_share_pct") or _NA, 40)],
            ["Top 10 share of revenue", _clean(concentration.get("top_10_share_pct") or _NA, 40)],
            [
                "Concentration index",
                _clean(concentration.get("concentration_index") or _NA, 200),
            ],
            [
                "Top 1 share of gross profit",
                _clean(concentration.get("gross_profit_top_1_share_pct") or _NA, 40),
            ],
            [
                "Top 5 share of gross profit",
                _clean(concentration.get("gross_profit_top_5_share_pct") or _NA, 40),
            ],
            ["Calculation notes", _clean(concentration.get("calculation_notes"), 420)],
            ["Risk rating", _clean(concentration.get("risk_rating") or _WITHHELD, 220)],
            ["Source", _clean(concentration.get("source") or _NA, 60)],
        ]
        parts.append(_table(["Measure", "Value"], rows))
        if not _is_filled(concentration.get("gross_profit_top_1_share_pct")) and not _is_filled(
            concentration.get("gross_profit_top_5_share_pct")
        ):
            parts.append(
                "*Gross profit concentration is not calculated — customer-level margin "
                "data were not opened. It is requested rather than estimated from "
                "revenue shares.*\n\n"
            )
    else:
        parts.append(
            "**Concentration is unassessed.** The billing ledger / investor workbook at "
            "parent level was not opened, so top 1 / top 5 / top 10 revenue shares "
            "cannot be calculated. Qualitative statements about concentration in the "
            "packs are descriptions, not calculations, and are not adopted here.\n\n"
        )
        parts.append(_table(
            ["Measure", "Value"],
            [
                ["Population", "parents (required basis — related accounts rolled up)"],
                ["Top 1 share of revenue", "Unassessed — not calculable"],
                ["Top 5 share of revenue", "Unassessed — not calculable"],
                ["Top 10 share of revenue", "Unassessed — not calculable"],
                ["Concentration index", "Unassessed — not calculable"],
                ["Top 1 / Top 5 share of gross profit", "Unassessed — not calculable"],
                ["Calculation notes", _clean(concentration.get("calculation_notes"), 420)],
                ["Risk rating", "**withheld**"],
                ["Source", _clean(concentration.get("source") or _NA, 60)],
            ],
        ))
        req = _clean(
            concentration.get("information_request")
            or _info_request(
                "customer-level revenue by parent for the audited period so top 1 / "
                "top 5 / top 10 shares and a concentration index can be calculated"
            ),
            340,
        )
        parts.append(f"**{req}**\n\n")
        parts.append(
            "*Risk rating is **withheld** while concentration is unassessed. An empty "
            "concentration table is **not** a high-risk finding — absence of the ledger "
            "is an information gap, not evidence of exposure.*\n\n"
        )
    parts.append("---\n\n")

    # --- 4 ----------------------------------------------------------------
    parts.append("## 4. Largest Contracts\n\n")
    parts.append(
        "The largest contracts are named with value, share of revenue, end date and "
        "termination rights. Where a counterparty is not named in the packs, the name "
        "is requested — never invented.\n\n"
    )
    if contracts:
        parts.append(_table(
            [
                "Contract / Counterparty", "Value", "Share of revenue", "End date",
                "Termination rights", "Source",
            ],
            [
                [
                    _clean(c.get("name"), 70),
                    _clean(c.get("value"), 80),
                    _clean(c.get("share_pct"), 60),
                    _clean(c.get("end_date"), 70),
                    _clean(c.get("termination_rights"), 160),
                    _clean(c.get("source") or _NA, 40),
                ]
                for c in contracts if isinstance(c, dict)
            ],
        ))
    else:
        parts.append(
            "No contract register was opened, so no contract is named. The register is "
            "requested rather than reconstructed from prose.\n\n"
        )
    parts.append("---\n\n")

    # --- 5 ----------------------------------------------------------------
    parts.append("## 5. Population Discipline\n\n")
    parts.append(
        "Counts are meaningless without their population. Accounts, parents, locations "
        "and subscriptions are reported separately and are never mixed in one table.\n\n"
    )
    parts.append(_table(
        ["Item", "Statement"],
        [
            [
                "Population statement",
                _clean(
                    discipline.get("statement")
                    or (
                        f"Primary population is {primary_pop}; concentration is computed "
                        "on parents. Populations are not mixed within a table."
                    ),
                    460,
                ),
            ],
            [
                "Caveats",
                _clean(
                    discipline.get("caveats")
                    or "Limits stated in the sections above.",
                    460,
                ),
            ],
        ],
    ))
    parts.append(
        "*This section does not recommend invest or pass. Where concentration cannot be "
        "calculated from parent-level revenue, it is unassessed: the ledger is "
        "requested and any risk rating is withheld. An empty concentration table is not "
        "a high-risk finding, and revenue that cannot be classified is shown as an "
        "unclassified remainder rather than forced into a segment.*\n\n"
    )
    parts.append("---\n\n")

    # --- 6 ----------------------------------------------------------------
    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(spec.get("quality_verdict") or "PASS", 30)],
            ["Reliance Verdict", _clean(spec.get("reliance_verdict") or "LIMITED", 30)],
            [
                "Rationale",
                _clean(
                    spec.get("quality_reliance_rationale")
                    or "Limits stated in the sections above.",
                    460,
                ),
            ],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can diligence rest on this segmentation and concentration arithmetic?\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(list(srcs)[:16], start=1):
            parts.append(f"[{i}] {_clean(name, 120)}\n")
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n\n")

    return "".join(parts)
