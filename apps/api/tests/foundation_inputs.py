"""Documents that bind every foundation role.

A later-phase test has to upload these. A role with none of its document
kinds is stored as needs repair and does not complete the phase.
"""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

FOUNDATION_FILES: tuple[tuple[str, bytes], ...] = (
    ("Process Letter.txt", b"Process letter with the bidding timeline."),
    ("NDA.txt", b"Non-disclosure agreement."),
    ("Articles of Incorporation.txt", b"Articles of incorporation of the target."),
    ("Org Chart.txt", b"Org chart. CEO and CFO."),
    ("Technical Due Diligence.txt", b"Technical due diligence. Software and IP."),
    ("Legal Compliance.txt", b"Legal compliance review."),
    ("Investment Thesis.txt", b"Investment thesis and strategic rationale."),
)


ANALYSIS_FILES: tuple[tuple[str, bytes], ...] = (
    ("Market Overview.txt", b"Market overview. TAM SAM competition and share."),
    ("Customer Retention.txt", b"Customer churn retention and cohort."),
    ("Financial Due Diligence.txt", b"Revenue EBITDA and financial statements."),
    ("Operational Review.txt", b"Operations supply chain and manufacturing."),
)


def upload_named_files(
    client: TestClient,
    headers: dict[str, str],
    deal_id: str,
    files: tuple[tuple[str, bytes], ...],
) -> None:
    for name, body in files:
        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": (name, BytesIO(body), "text/plain")},
        )
        assert upload.status_code == 200, name


def upload_foundation_inputs(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    upload_named_files(client, headers, deal_id, FOUNDATION_FILES)


def upload_analysis_inputs(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    """Foundation kinds plus one file for each later-phase category."""
    upload_foundation_inputs(client, headers, deal_id)
    upload_named_files(client, headers, deal_id, ANALYSIS_FILES)

