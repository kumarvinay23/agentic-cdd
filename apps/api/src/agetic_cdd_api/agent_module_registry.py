"""One approved module version per catalog agent.

A run is stored as completed only when its output names that module and
its required input is present. A retired module, or a run with no required
input, is stored as needs_repair.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from agetic_cdd_api.pipeline_catalog import all_agent_keys

APPROVED_VERSION = "1"
APPROVED_REGULATORY_MODULE = "agent_document_regulatory_compliance"
RETIRED_REGULATORY_MODULE = "foundation_extractors.F-04"
RETIRED_MODULE_IDS = frozenset({RETIRED_REGULATORY_MODULE})
# These agents have a known older copy. They must name the approved module
# themselves. A missing id is not filled in on their behalf.
EXPLICIT_MODULE_AGENTS = frozenset({"regulatory_compliance"})
APPROVED_REGULATORY_COMPOSERS = frozenset({"heuristic_v1", "llm_v1"})
_SOURCED_VERDICTS = frozenset({"PASS", "CLOSED", "READY"})
_VERDICT_KEYS = frozenset({"quality_verdict", "reliance_verdict", "verdict", "status"})
_VERDICT_DOWNGRADE = {"PASS": "REWORK", "READY": "LIMITED", "CLOSED": "OPEN"}
_FILE_SOURCE = re.compile(
    r"(?i)(?:https?://\S+|(?:^|[\s:(])[\w][\w .()\-]{0,120}\.(?:pdf|xlsx|xls|xlsm|docx|doc|pptx|csv|txt|md)\b|\b(?:page|slide|sheet|cell|tab)\s*[:#]?\s*[A-Za-z]?\d+)"
)


def duplicate_agent_keys() -> list[str]:
    keys = all_agent_keys()
    return sorted({key for key in keys if keys.count(key) != 1})


def approved_module_id(agent_key: str) -> str | None:
    """The single module allowed to complete this agent, or None if the key is not unique."""
    if agent_key in duplicate_agent_keys() or agent_key not in all_agent_keys():
        return None
    if agent_key == "regulatory_compliance":
        return APPROVED_REGULATORY_MODULE
    return f"pipeline.{agent_key}"


def _is_specific_source(text: str) -> bool:
    """A filename, URL, page, slide, sheet, or cell. A generic data-room label is not one."""
    cleaned = text.strip()
    if not cleaned:
        return False
    if re.search(r"(?i)\b(?:information request|not stated|did not provide|n/?a\b|data room financials)\b", cleaned):
        if not _FILE_SOURCE.search(cleaned):
            return False
    return _FILE_SOURCE.search(cleaned) is not None


def _source_strings(node: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in (
        "source",
        "sources",
        "primary_sources",
        "citation",
        "citations",
        "evidence",
        "document",
        "filename",
        "file",
        "url",
        "detail",
        "notes",
    ):
        value = node.get(key)
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, list):
            found.extend(str(item) for item in value if isinstance(item, str))
    return found


def _has_specific_source(node: dict[str, Any]) -> bool:
    return any(_is_specific_source(item) for item in _source_strings(node))


def _output_names_a_source(output: dict[str, Any]) -> bool:
    if _has_specific_source(output):
        return True
    spec = output.get("spec")
    return isinstance(spec, dict) and _has_specific_source(spec)


def withhold_unsourced_verdicts(output: dict[str, Any]) -> dict[str, Any]:
    """PASS, CLOSED, and READY stay only when a specific source is named.

    CLOSED must be named on that verdict. PASS and READY may use a source
    named on the output. Anything else is downgraded and not published.
    """
    out = copy.deepcopy(output)
    supported = _output_names_a_source(out)
    withheld: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            local = _has_specific_source(node)
            for key, value in list(node.items()):
                if isinstance(value, str) and key in _VERDICT_KEYS:
                    word = value.strip().upper()
                    if word not in _SOURCED_VERDICTS:
                        continue
                    named = local if word == "CLOSED" else (local or supported)
                    if named:
                        continue
                    replacement = "FAIL" if key == "status" and word == "PASS" else _VERDICT_DOWNGRADE[word]
                    node[key] = replacement
                    withheld.append(f"{key} {word} withheld: no specific source")
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(out)
    if withheld:
        out["verdicts_withheld"] = withheld
    return out


def missing_required_input(output: dict[str, Any]) -> str | None:
    """Why this output cannot complete, or None when its required input is present.

    A default, a fixture, or an empty-room skeleton is not a required input.
    Partial coverage still counts: at least one bound source was present.
    """
    if output.get("stub") is True:
        return "fixture output has no required inputs"
    if output.get("empty_vdr") is True or str(output.get("status") or "") == "empty_vdr":
        return "required data-room input is missing"
    # An upstream store is a real input. A missing data-room bind with no
    # store and no document is a default, and must not complete.
    extract = str(output.get("extract_source") or "")
    if str(output.get("source_coverage") or "") == "missing" and extract not in {"vdr", "stores"}:
        return "required data-room input is missing"
    missing = output.get("missing_inputs")
    if isinstance(missing, list):
        names = [str(item).strip() for item in missing if str(item).strip()]
        if names:
            return "missing required input: " + ", ".join(names[:6])
    if "document_count" in output and not output.get("document_count") and not output.get("sources"):
        return "required data-room input is missing"
    return None


def _regulatory_composer(output: dict[str, Any]) -> str:
    spec = output.get("spec")
    if not isinstance(spec, dict):
        return ""
    return str(spec.get("composer") or "")


def prepare_completion(agent_key: str, output: dict[str, Any]) -> dict[str, Any]:
    """Return the output that may be stored. Unapproved modules are needs_repair."""
    from agetic_cdd_api.agent_contracts import apply_contract

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        return apply_contract(agent_key, payload)

    out = withhold_unsourced_verdicts(output)
    status = str(out.get("status") or "")
    if status == "failed":
        return finish(out)

    approved = approved_module_id(agent_key)
    module = str(out.get("module_id") or "")
    if (
        approved is None
        or module in RETIRED_MODULE_IDS
        or (module and module != approved)
    ):
        out["status"] = "needs_repair"
        out["error"] = (
            f"{agent_key} module {module or 'missing'} is not the approved module "
            f"{approved or 'none'}"
        )
        return finish(out)

    if agent_key == "regulatory_compliance":
        if _regulatory_composer(out) not in APPROVED_REGULATORY_COMPOSERS:
            out["status"] = "needs_repair"
            out["module_id"] = module or RETIRED_REGULATORY_MODULE
            out["error"] = (
                "regulatory_compliance did not run "
                f"{APPROVED_REGULATORY_MODULE}"
            )
            return finish(out)

    if not module:
        if agent_key in EXPLICIT_MODULE_AGENTS or not approved:
            out["status"] = "needs_repair"
            out["error"] = f"{agent_key} ran without the approved module id"
            return finish(out)
        out["module_id"] = approved
        out["module_version"] = APPROVED_VERSION

    gap = missing_required_input(out)
    if gap:
        out["status"] = "needs_repair"
        out["error"] = gap
        return finish(out)

    if status not in {"completed", "empty_vdr", "needs_repair"}:
        out["status"] = "completed"
    elif not status:
        out["status"] = "completed"
    return finish(out)
