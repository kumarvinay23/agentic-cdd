"""Retrieval benchmark — FTS + passage recall matrix for Document Workspace."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agetic_cdd_api.document_capabilities import capability_by_id
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_document_runner import (
    _CAP_CATEGORIES,
    retrieve_passages,
)
from agetic_cdd_api.services_library_search import search_library_chunks

DEFAULT_COMPANY = "Ola Electric"
DEFAULT_VDR_FILE_COUNT = 105
MIN_FTS_RECALL = 0.85
MIN_PASSAGE_RECALL = 0.80


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    prompt: str
    capability_id: str
    expected_file_patterns: tuple[str, ...]
    min_fts_hits: int = 1
    min_passage_sources: int = 1


@dataclass
class CaseResult:
    case_id: str
    prompt: str
    capability_id: str
    fts_hits: int
    fts_recall: bool
    fts_top1: bool
    passage_sources: int
    passage_recall: bool
    passage_top1: bool
    top_fts_file: str | None = None
    top_passage_file: str | None = None
    expected_patterns: list[str] = field(default_factory=list)
    passed: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class RetrievalBenchmarkReport:
    deal_id: str
    company: str
    document_count: int
    indexed_chunks: int
    case_results: list[CaseResult] = field(default_factory=list)

    @property
    def case_total(self) -> int:
        return len(self.case_results)

    @property
    def fts_recall_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for r in self.case_results if r.fts_recall) / len(self.case_results)

    @property
    def passage_recall_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for r in self.case_results if r.passage_recall) / len(self.case_results)

    @property
    def fts_top1_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for r in self.case_results if r.fts_top1) / len(self.case_results)

    @property
    def passage_top1_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for r in self.case_results if r.passage_top1) / len(self.case_results)

    @property
    def passed(self) -> bool:
        return (
            self.fts_recall_rate >= MIN_FTS_RECALL
            and self.passage_recall_rate >= MIN_PASSAGE_RECALL
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal_id": self.deal_id,
            "company": self.company,
            "document_count": self.document_count,
            "indexed_chunks": self.indexed_chunks,
            "case_total": self.case_total,
            "fts_recall_rate": round(self.fts_recall_rate, 3),
            "passage_recall_rate": round(self.passage_recall_rate, 3),
            "fts_top1_rate": round(self.fts_top1_rate, 3),
            "passage_top1_rate": round(self.passage_top1_rate, 3),
            "passed": self.passed,
            "thresholds": {
                "min_fts_recall": MIN_FTS_RECALL,
                "min_passage_recall": MIN_PASSAGE_RECALL,
            },
            "cases": [asdict(r) for r in self.case_results],
        }


# 20 standard CDD retrieval prompts with expected VDR filename signals.
BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        "market_share",
        "Research this and add a section to the document: What is {company}'s market share?",
        "mkt_marimekko_segments",
        ("Market_Competition",),
    ),
    BenchmarkCase(
        "growth_rate",
        "Research this and add a section to the document: What is the revenue growth rate of {company}?",
        "growth_trend",
        ("Financial_Due_Diligence", "Financial"),
    ),
    BenchmarkCase(
        "yoy_growth",
        "Research this and add a section to the document: What is {company}'s YoY revenue growth?",
        "gx_yoy_scorecard",
        ("Financial_Due_Diligence",),
    ),
    BenchmarkCase(
        "cagr",
        "Research this and add a section to the document: What is {company}'s revenue CAGR?",
        "gx_cagr_momentum",
        ("Financial_Due_Diligence",),
    ),
    BenchmarkCase(
        "competitors",
        "Research this and add a section to the document: Who are the main competitors of {company}?",
        "investment_thesis",
        ("Market_Competition", "Investment_Thesis"),
    ),
    BenchmarkCase(
        "investment_thesis",
        "Research this and add a section to the document: What is {company}'s investment thesis?",
        "investment_thesis",
        ("Investment_Thesis",),
    ),
    BenchmarkCase(
        "business_model",
        "Research this and add a section to the document: How does {company}'s business model work?",
        "narr_investment_summary",
        ("Investment_Thesis", "Corporate_Overview", "Commercial_Due_Diligence"),
    ),
    BenchmarkCase(
        "key_risks",
        "Research this and add a section to the document: What are the key investment risks for {company}?",
        "risk_assessment",
        ("Legal_Due_Diligence", "Investment_Thesis", "Operational_Due_Diligence"),
    ),
    BenchmarkCase(
        "market_overview",
        "Research this and add a section to the document: Provide a market overview for {company}.",
        "mkt_tam_sam_ovals",
        ("Market_Competition",),
    ),
    BenchmarkCase(
        "penetration",
        "Research this and add a section to the document: What is the EV penetration rate in {company}'s market?",
        "mkt_size_vs_penetration_combo",
        ("Market_Competition",),
    ),
    BenchmarkCase(
        "tam_sam",
        "Research this and add a section to the document: What is the TAM and SAM for {company}?",
        "mkt_tam_sam_ovals",
        ("Market_Competition", "Investment_Thesis"),
    ),
    BenchmarkCase(
        "margin",
        "Research this and add a section to the document: What is {company}'s EBITDA margin trend?",
        "margin_bridge",
        ("Financial_Due_Diligence",),
    ),
    BenchmarkCase(
        "valuation",
        "Research this and add a section to the document: What is the implied valuation of {company}?",
        "implied_valuation",
        ("Valuation", "Financial_Due_Diligence"),
    ),
    BenchmarkCase(
        "customer_retention",
        "Research this and add a section to the document: What is {company}'s customer churn and retention?",
        "gen_geographic_mix",
        ("Commercial_Due_Diligence",),
    ),
    BenchmarkCase(
        "management",
        "Research this and add a section to the document: Who leads {company}'s management team?",
        "kpi_scorecard",
        ("Corporate_Overview", "HR"),
    ),
    BenchmarkCase(
        "legal",
        "Research this and add a section to the document: What legal and compliance issues affect {company}?",
        "narr_risks_mitigants",
        ("Legal_Due_Diligence",),
    ),
    BenchmarkCase(
        "operations",
        "Research this and add a section to the document: What are {company}'s operational and supply chain risks?",
        "risk_assessment",
        ("Operational_Due_Diligence",),
    ),
    BenchmarkCase(
        "technology",
        "Research this and add a section to the document: What is {company}'s technology and IP position?",
        "risk_assessment",
        ("Technical_Due_Diligence",),
    ),
    BenchmarkCase(
        "geography",
        "Research this and add a section to the document: What is {company}'s geographic revenue mix?",
        "gen_geographic_mix",
        ("Commercial_Due_Diligence", "Market_Competition"),
    ),
    BenchmarkCase(
        "sales_ratio",
        "Research this and add a section to the document: What is the sales / channel mix ratio for {company}?",
        "mkt_marimekko_segments",
        ("Commercial_Due_Diligence", "Market_Competition"),
    ),
)


def synthetic_benchmark_vdr(count: int = DEFAULT_VDR_FILE_COUNT) -> list[tuple[str, str]]:
    """Generate a large synthetic VDR with CDL-shaped filenames for scale testing."""
    patterns: list[tuple[str, str]] = [
        (
            "11_Market_Competition_{i}.txt",
            (
                "Market competition analysis for Ola Electric. Market share {i} percent FY2024. "
                "TAM SAM SOM penetration rate competitive landscape marimekko segment mix."
            ),
        ),
        (
            "05_Financial_Due_Diligence_{i}.txt",
            (
                "Financial due diligence for Ola Electric. Revenue growth rate {i} percent YoY. "
                "Revenue CAGR compound annual growth rate EBITDA margin bridge valuation sensitivity."
            ),
        ),
        (
            "03_Investment_Thesis_{i}.txt",
            (
                "Investment thesis for Ola Electric. Growth strategy business model expansion plan. "
                "Key investment risks mitigants competitor positioning."
            ),
        ),
        (
            "06_Legal_Due_Diligence_{i}.txt",
            (
                "Legal due diligence for Ola Electric. Legal compliance contract litigation "
                "regulatory summary compliance issues."
            ),
        ),
        (
            "02_Corporate_Overview_{i}.txt",
            (
                "Corporate overview for Ola Electric. Management team board biography headquarters "
                "leadership organizational structure."
            ),
        ),
        (
            "04_Commercial_Due_Diligence_{i}.txt",
            (
                "Commercial due diligence for Ola Electric. Customer churn rate NPS retention cohort "
                "geographic revenue mix sales channel ratio commercial metrics."
            ),
        ),
        (
            "07_Operational_Due_Diligence_{i}.txt",
            (
                "Operational due diligence for Ola Electric. Manufacturing supply chain operations "
                "capacity supplier operational risk review."
            ),
        ),
        (
            "08_Technical_Due_Diligence_{i}.txt",
            (
                "Technical due diligence for Ola Electric. Software architecture patent technology "
                "stack IP product roadmap technical IP position R&D engineering."
            ),
        ),
        (
            "13_Valuation_Analysis_{i}.txt",
            (
                "Valuation analysis for Ola Electric. Implied valuation comparable multiples "
                "EV EBITDA DCF sensitivity trading comps."
            ),
        ),
        (
            "10_HR_Organizational_{i}.txt",
            (
                "HR organizational structure for Ola Electric. Management team depth human capital "
                "workforce review leadership bench."
            ),
        ),
    ]
    out: list[tuple[str, str]] = []
    for n in range(count):
        template, body = patterns[n % len(patterns)]
        out.append((template.format(i=n), body.format(i=n)))
    return out


def _filename_matches(filename: str, patterns: tuple[str, ...]) -> bool:
    hay = filename.lower()
    return any(p.lower().replace("_", " ") in hay.replace("_", " ") or p.lower() in hay for p in patterns)


def _evaluate_case(
    deal: Deal,
    *,
    case: BenchmarkCase,
    prompt: str,
    index: dict[str, Any],
) -> CaseResult:
    cap = capability_by_id(case.capability_id)
    if cap is None:
        return CaseResult(
            case_id=case.case_id,
            prompt=prompt,
            capability_id=case.capability_id,
            fts_hits=0,
            fts_recall=False,
            fts_top1=False,
            passage_sources=0,
            passage_recall=False,
            passage_top1=False,
            expected_patterns=list(case.expected_file_patterns),
            notes=[f"unknown capability {case.capability_id}"],
        )

    categories = set(_CAP_CATEGORIES.get(case.capability_id, ()))
    cap_title = str(cap.get("title") or "")
    query = f"{prompt} {cap_title}".strip()

    fts_hits = search_library_chunks(
        deal,
        query=query,
        categories=categories or None,
        limit=24,
        index=index,
    )
    fts_files = [str(h.get("filename") or "") for h in fts_hits]
    fts_recall = any(_filename_matches(f, case.expected_file_patterns) for f in fts_files)
    fts_top1 = bool(fts_files) and _filename_matches(fts_files[0], case.expected_file_patterns)

    sources = retrieve_passages(deal, prompt=prompt, capability=cap, index=index)
    passage_files = [str(s.get("title") or "") for s in sources]
    passage_recall = any(_filename_matches(f, case.expected_file_patterns) for f in passage_files)
    passage_top1 = bool(passage_files) and _filename_matches(passage_files[0], case.expected_file_patterns)

    notes: list[str] = []
    if len(fts_hits) < case.min_fts_hits:
        notes.append(f"fts hits {len(fts_hits)} < {case.min_fts_hits}")
    if len(sources) < case.min_passage_sources:
        notes.append(f"passage sources {len(sources)} < {case.min_passage_sources}")
    if not fts_recall:
        notes.append(f"no FTS file matched {case.expected_file_patterns}")
    if not passage_recall:
        notes.append(f"no passage file matched {case.expected_file_patterns}")

    passed = (
        fts_recall
        and passage_recall
        and len(fts_hits) >= case.min_fts_hits
        and len(sources) >= case.min_passage_sources
    )

    return CaseResult(
        case_id=case.case_id,
        prompt=prompt,
        capability_id=case.capability_id,
        fts_hits=len(fts_hits),
        fts_recall=fts_recall,
        fts_top1=fts_top1,
        passage_sources=len(sources),
        passage_recall=passage_recall,
        passage_top1=passage_top1,
        top_fts_file=fts_files[0] if fts_files else None,
        top_passage_file=passage_files[0] if passage_files else None,
        expected_patterns=list(case.expected_file_patterns),
        passed=passed,
        notes=notes,
    )


def run_retrieval_benchmark(
    deal: Deal,
    index: dict[str, Any],
    *,
    company: str = DEFAULT_COMPANY,
    document_count: int = 0,
    indexed_chunks: int = 0,
    cases: tuple[BenchmarkCase, ...] = BENCHMARK_CASES,
) -> RetrievalBenchmarkReport:
    """Run the full retrieval matrix against an indexed deal library."""
    report = RetrievalBenchmarkReport(
        deal_id=deal.id,
        company=company,
        document_count=document_count,
        indexed_chunks=indexed_chunks,
    )
    for case in cases:
        prompt = case.prompt.format(company=company)
        report.case_results.append(
            _evaluate_case(deal, case=case, prompt=prompt, index=index)
        )
    return report


def format_benchmark_report(report: RetrievalBenchmarkReport) -> str:
    lines = [
        f"\nRetrieval Benchmark — {report.company}",
        "=" * 56,
        f"Deal ID:              {report.deal_id}",
        f"VDR documents:        {report.document_count}",
        f"FTS chunks indexed:   {report.indexed_chunks}",
        f"Cases:                {report.case_total}",
        f"FTS recall@any:       {report.fts_recall_rate:.0%} (threshold {MIN_FTS_RECALL:.0%})",
        f"Passage recall@any:   {report.passage_recall_rate:.0%} (threshold {MIN_PASSAGE_RECALL:.0%})",
        f"FTS top-1 accuracy:   {report.fts_top1_rate:.0%}",
        f"Passage top-1:        {report.passage_top1_rate:.0%}",
        f"Overall:              {'PASS' if report.passed else 'FAIL'}",
        "",
    ]
    for result in report.case_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"  [{status}] {result.case_id}")
        lines.append(
            f"         fts={result.fts_hits} recall={result.fts_recall} top1={result.fts_top1}"
            f" | passages={result.passage_sources} recall={result.passage_recall} top1={result.passage_top1}"
        )
        if result.top_passage_file:
            lines.append(f"         top passage file: {result.top_passage_file}")
        for note in result.notes:
            if not result.passed:
                lines.append(f"         - {note}")
    lines.append("")
    return "\n".join(lines)
