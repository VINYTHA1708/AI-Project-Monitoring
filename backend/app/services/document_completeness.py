import re
from typing import Callable

from app.services.document_extractor import extract_pdf_text_from_upload

DEFAULT_REPORT_SECTIONS = [
    "Abstract",
    "Introduction",
    "Problem Statement",
    "Objectives",
    "Methodology",
    "Implementation",
    "Results and Discussion",
    "Conclusion",
    "References",
]

DEFAULT_SRS_SECTIONS = [
    "Introduction",
    "Purpose and Scope",
    "Overall Description",
    "Functional Requirements",
    "Non-Functional Requirements",
    "System Requirements",
    "Use Cases",
    "Constraints",
    "References",
]

DOCUMENT_SECTION_MAP = {
    "project_report": DEFAULT_REPORT_SECTIONS,
    "report": DEFAULT_REPORT_SECTIONS,
    "srs": DEFAULT_SRS_SECTIONS,
    "software_requirements_specification": DEFAULT_SRS_SECTIONS,
}


SECTION_RATIONALES: dict[str, str] = {
    "Abstract": "Provides an executive summary of the project scope, methodology, and key contributions.",
    "Introduction": "Establishes contextual background, project significance, and core motivations.",
    "Problem Statement": "Articulates the specific technical problem or research challenge being solved.",
    "Objectives": "Defines clear, measurable project targets and expected milestones.",
    "Methodology": "Describes the technical strategy, design principles, and engineering workflow.",
    "Implementation": "Documents concrete software engineering artifacts, tools, and technical details.",
    "Results and Discussion": "Presents empirical evaluation, validation metrics, and critical discussion.",
    "Conclusion": "Summarizes project outcomes, highlights impact, and outlines future enhancements.",
    "References": "Credits academic sources and technical foundations to ensure academic integrity.",
    "Purpose and Scope": "Defines software product boundaries, stakeholders, and high-level objectives.",
    "Overall Description": "Provides high-level system perspective, operational context, and user constraints.",
    "Functional Requirements": "Specifies concrete system behaviors, functional capabilities, inputs, and outputs.",
    "Non-Functional Requirements": "Defines performance benchmarks, security expectations, and quality standards.",
    "System Requirements": "Specifies hardware, software, runtime environment, and dependency prerequisites.",
    "Use Cases": "Maps out user interaction scenarios, operational flows, and functional behaviors.",
    "Constraints": "Identifies architectural limits, regulatory requirements, and technical boundaries.",
}

ANALYSIS_LIMITATION_DISCLAIMER = (
    "Structural completeness analysis verifies the presence of recognized section headings "
    "and document length. It does not verify the technical accuracy, semantic depth, "
    "or substantive correctness of the content."
)


def get_required_sections(
    document_type: str,
    required_sections: list[str] | None = None,
) -> list[str]:
    normalized_document_type = str(document_type or "").strip().lower().replace("-", "_")
    defaults = DOCUMENT_SECTION_MAP.get(normalized_document_type, [])
    if required_sections is not None:
        return required_sections
    return defaults[:]


def normalize_section_name(value: str) -> str:
    if value is None:
        return ""

    text = str(value).replace("&", " and ")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"^\s*[-*•\d.\)]+\s*", "", text)
    text = re.sub(r"[:;\-]+$", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _build_section_variants(section_name: str) -> set[str]:
    normalized = normalize_section_name(section_name)
    variants = {normalized}

    if not normalized:
        return variants

    if " and " in normalized:
        variants.add(normalized.replace(" and ", " "))

    if " " in normalized:
        variants.add(normalized.replace(" ", ""))

    return {variant for variant in variants if variant}


def _is_heading_like(line: str, allowed_aliases: set[str]) -> bool:
    cleaned = re.sub(r"^[-*•\s]+", "", line.strip())
    cleaned = re.sub(r"^(?:chapter|section|part|module)\s+[\w\d]+[:.\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[0-9]+(?:\.[0-9]+)*[\.)\-]?\s*", "", cleaned)
    cleaned = re.sub(r"^[ivxlcdm]+[\.)\-]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    if not cleaned:
        return False

    if len(cleaned.split()) > 8:
        return False

    normalized = normalize_section_name(cleaned)
    if not normalized:
        return False

    if normalized in allowed_aliases:
        return True

    for alias in sorted(allowed_aliases, key=len, reverse=True):
        if normalized == alias or normalized.endswith(f" {alias}"):
            return True
        if normalized.startswith(f"{alias} "):
            return True

    return False


def detect_sections_in_text(text: str, required_sections: list[str]) -> tuple[list[str], list[str]]:
    aliases_by_section: dict[str, set[str]] = {
        section: _build_section_variants(section)
        for section in required_sections
    }
    all_aliases = {alias for aliases in aliases_by_section.values() for alias in aliases}

    detected: list[str] = []
    for section in required_sections:
        aliases = aliases_by_section[section]
        if any(
            _is_heading_like(line, aliases)
            for line in (text or "").splitlines()
        ):
            detected.append(section)

    missing = [section for section in required_sections if section not in detected]
    return detected, missing


def analyze_document_completeness(
    document_type: str,
    file_name: str | object,
    required_sections: list[str] | None = None,
    extraction_fn: Callable[[str | object], dict] | None = None,
) -> dict:
    extraction_function = extraction_fn or extract_pdf_text_from_upload
    section_requirements = get_required_sections(document_type, required_sections)

    extraction_result = extraction_function(file_name)
    extraction_status = extraction_result.get("status", "failed")
    extraction_error = extraction_result.get("error", "")

    warnings: list[str] = []
    extraction_errors: list[str] = []

    if extraction_status in {"failed", "no_text_found"}:
        if extraction_error:
            extraction_errors.append(extraction_error)
        if extraction_status == "no_text_found":
            warnings.append(
                "No selectable text was found. OCR is not implemented in this phase."
            )
        return {
            "document_type": document_type,
            "analysis_status": extraction_status,
            "completeness_percentage": None,
            "detected_sections": [],
            "missing_sections": section_requirements[:],
            "missing_section_details": [
                {
                    "section": s,
                    "rationale": SECTION_RATIONALES.get(
                        s, "Standard academic requirement for this document type."
                    ),
                }
                for s in section_requirements
            ],
            "limitation_disclaimer": ANALYSIS_LIMITATION_DISCLAIMER,
            "page_count": extraction_result.get("page_count", 0),
            "word_count": extraction_result.get("word_count", 0),
            "warnings": warnings,
            "extraction_errors": extraction_errors,
            "required_sections": section_requirements,
        }

    if extraction_status != "success":
        if extraction_error:
            extraction_errors.append(extraction_error)
        return {
            "document_type": document_type,
            "analysis_status": "failed",
            "completeness_percentage": None,
            "detected_sections": [],
            "missing_sections": section_requirements[:],
            "missing_section_details": [
                {
                    "section": s,
                    "rationale": SECTION_RATIONALES.get(
                        s, "Standard academic requirement for this document type."
                    ),
                }
                for s in section_requirements
            ],
            "limitation_disclaimer": ANALYSIS_LIMITATION_DISCLAIMER,
            "page_count": extraction_result.get("page_count", 0),
            "word_count": extraction_result.get("word_count", 0),
            "warnings": warnings,
            "extraction_errors": extraction_errors,
            "required_sections": section_requirements,
        }

    extracted_text = extraction_result.get("extracted_text", "")
    page_count = extraction_result.get("page_count", 0)
    word_count = extraction_result.get("word_count", 0)

    if page_count <= 0:
        warnings.append("No pages were returned by the extraction step.")
    if word_count <= 0:
        warnings.append("No words were extracted from the document.")
    elif word_count < 100:
        warnings.append("The document is unusually short for a detailed project report or SRS.")

    detected_sections, missing_sections = detect_sections_in_text(extracted_text, section_requirements)
    completeness_percentage = (
        round((len(detected_sections) / len(section_requirements)) * 100, 2)
        if section_requirements
        else 100.0
    )

    analysis_status = (
        "complete" if completeness_percentage == 100 else "incomplete"
    )

    missing_section_details = [
        {
            "section": s,
            "rationale": SECTION_RATIONALES.get(
                s, "Standard academic requirement for this document type."
            ),
        }
        for s in missing_sections
    ]

    return {
        "document_type": document_type,
        "analysis_status": analysis_status,
        "completeness_percentage": completeness_percentage,
        "detected_sections": detected_sections,
        "missing_sections": missing_sections,
        "missing_section_details": missing_section_details,
        "limitation_disclaimer": ANALYSIS_LIMITATION_DISCLAIMER,
        "page_count": page_count,
        "word_count": word_count,
        "warnings": warnings,
        "extraction_errors": extraction_errors,
        "required_sections": section_requirements,
    }
