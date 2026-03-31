"""
Stage 1 — Seller Registration Validation.

Validates all fields in a seller registration request before any
profile is created or persisted.

Validation rules:
  - display_name:              required, 3–80 chars
  - description:               required, 20–2000 chars
  - specialization_categories: at least one valid TaskCategory
  - supported_output_types:    at least one valid OutputType
  - pricing_model:             must be FIXED or QUOTED (not FREE)
  - base_price:                required and > 0 when pricing_model = FIXED
  - estimated_minutes:         1–10080 (1 week max)
  - capacity:                  1–100
  - confidence_score:          0.1–1.0
  - expertise_claims:          at least one, each ≤ 300 chars
  - contact_email:             basic format check if provided

Returns a ValidationResult dataclass — never raises.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

VALID_CATEGORIES = {
    "financial_research",
    "legal_analysis",
    "market_intelligence",
    "strategy_business_research",
}
VALID_OUTPUT_TYPES = {"report", "summary", "structured_json", "bullet_list"}
VALID_PRICING_MODELS = {"fixed", "quoted"}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_seller_registration(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate a seller registration payload dict.

    Args:
        data: raw dict from the API request body (pre-Pydantic coercion).

    Returns:
        ValidationResult with valid=True if all checks pass.
    """
    result = ValidationResult(valid=True)

    # --- display_name ---
    name = data.get("display_name", "")
    if not name or not name.strip():
        result.add_error("display_name is required.")
    elif len(name.strip()) < 3:
        result.add_error("display_name must be at least 3 characters.")
    elif len(name.strip()) > 80:
        result.add_error("display_name must be 80 characters or fewer.")

    # --- description ---
    desc = data.get("description", "")
    if not desc or not desc.strip():
        result.add_error("description is required.")
    elif len(desc.strip()) < 20:
        result.add_error("description must be at least 20 characters.")
    elif len(desc.strip()) > 2000:
        result.add_error("description must be 2000 characters or fewer.")

    # --- specialization_categories ---
    cats = data.get("specialization_categories", [])
    if not cats:
        result.add_error("At least one specialization_category is required.")
    else:
        invalid = [c for c in cats if c not in VALID_CATEGORIES]
        if invalid:
            result.add_error(
                f"Invalid specialization_categories: {invalid}. "
                f"Valid values: {sorted(VALID_CATEGORIES)}"
            )

    # --- supported_output_types ---
    output_types = data.get("supported_output_types", [])
    if not output_types:
        result.add_error("At least one supported_output_type is required.")
    else:
        invalid_ot = [t for t in output_types if t not in VALID_OUTPUT_TYPES]
        if invalid_ot:
            result.add_error(
                f"Invalid supported_output_types: {invalid_ot}. "
                f"Valid values: {sorted(VALID_OUTPUT_TYPES)}"
            )

    # --- pricing_model ---
    pricing_model = data.get("pricing_model", "")
    if pricing_model not in VALID_PRICING_MODELS:
        result.add_error(
            f"pricing_model must be one of {sorted(VALID_PRICING_MODELS)}. "
            f"(FREE is reserved for the generalist baseline.)"
        )

    # --- base_price (required for FIXED pricing) ---
    base_price = data.get("base_price")
    if pricing_model == "fixed":
        if base_price is None:
            result.add_error("base_price is required when pricing_model is 'fixed'.")
        elif not isinstance(base_price, (int, float)) or base_price <= 0:
            result.add_error("base_price must be a positive number.")
        elif base_price > 100_000:
            result.add_warning("base_price is unusually high (> $100,000). Verify this is correct.")

    # --- estimated_minutes ---
    eta = data.get("estimated_minutes", 30)
    if not isinstance(eta, int) or eta < 1:
        result.add_error("estimated_minutes must be a positive integer.")
    elif eta > 10_080:
        result.add_error("estimated_minutes cannot exceed 10,080 (1 week).")

    # --- capacity ---
    cap = data.get("capacity", 10)
    if not isinstance(cap, int) or cap < 1:
        result.add_error("capacity must be a positive integer.")
    elif cap > 100:
        result.add_warning("capacity > 100 is unusually high. Auditor will verify.")

    # --- confidence_score ---
    conf = data.get("confidence_score", 0.75)
    if not isinstance(conf, (int, float)) or conf < 0.1 or conf > 1.0:
        result.add_error("confidence_score must be a number between 0.1 and 1.0.")
    elif conf > 0.95:
        result.add_warning(
            "confidence_score > 0.95 is very high. "
            "Auditor will scrutinize expertise claims carefully."
        )

    # --- expertise_claims ---
    claims = data.get("expertise_claims", [])
    if not claims:
        result.add_error(
            "At least one expertise_claim is required. "
            "Example: 'CFA charterholder with 8 years in equity research'"
        )
    else:
        long_claims = [c for c in claims if len(str(c)) > 300]
        if long_claims:
            result.add_error(
                f"{len(long_claims)} expertise_claim(s) exceed 300 characters. "
                "Keep each claim concise."
            )

    # --- contact_email (optional format check) ---
    email = data.get("contact_email")
    if email and not EMAIL_RE.match(str(email)):
        result.add_error(f"contact_email '{email}' does not appear to be a valid email address.")

    # --- website_url (optional format check) ---
    url = data.get("website_url")
    if url and not str(url).lower().startswith(("http://", "https://")):
        result.add_warning(
            f"website_url '{url}' does not start with http:// or https://. "
            "Verify this is intentional."
        )

    return result
