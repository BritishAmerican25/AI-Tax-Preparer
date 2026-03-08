"""Phase 3 – AI Tax Assistant.

Uses the OpenAI Chat Completions API to answer tax questions in the context
of the user's return.  All responses include a mandatory legal disclaimer.
"""

from __future__ import annotations

import logging

from openai import OpenAI, OpenAIError

from app.models.tax_return import (
    AIAssistantResponse,
    TaxCalculationResult,
    ComplianceCheckResult,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an AI-powered tax assistant embedded in a US federal income tax
preparation application. Your role is to help taxpayers understand their tax situation, explain
tax concepts in plain language, and suggest legal tax-optimization strategies.

Guidelines:
- Base your answers on the current US Internal Revenue Code (IRC) and IRS publications.
- Always reference the specific IRC section or IRS form/publication when relevant.
- NEVER give advice that encourages tax evasion or fraudulent reporting.
- ALWAYS remind users that AI-generated information is not a substitute for advice from a
  licensed CPA, Enrolled Agent (EA), or tax attorney.
- If a question is outside the scope of US federal taxes, politely say so.
- Keep responses concise and easy to understand for a non-expert audience."""


def _build_context_message(
    result: TaxCalculationResult | None,
    compliance: ComplianceCheckResult | None,
) -> str:
    """Build a context message containing the user's tax summary."""
    if result is None and compliance is None:
        return ""
    parts = ["Context about the user's tax return:"]
    if result:
        parts.append(
            f"- Filing status: {result.filing_status.value}\n"
            f"- Tax year: {result.tax_year}\n"
            f"- Gross income: ${result.gross_income:,.2f}\n"
            f"- AGI: ${result.adjusted_gross_income:,.2f}\n"
            f"- Taxable income: ${result.taxable_income:,.2f}\n"
            f"- Federal tax owed: ${result.federal_tax_owed:,.2f}\n"
            f"- Effective tax rate: {result.effective_tax_rate:.1%}\n"
            f"- Refund/(owed): ${result.refund_or_owed:,.2f}"
        )
    if compliance:
        parts.append(
            f"- Audit risk: {compliance.audit_risk_label} ({compliance.audit_risk_score:.0%})\n"
            f"- Compliance issues: {len(compliance.issues)}\n"
            f"- Compliance warnings: {len(compliance.warnings)}"
        )
    return "\n".join(parts)


def ask_assistant(
    question: str,
    api_key: str,
    model: str = "gpt-4o",
    result: TaxCalculationResult | None = None,
    compliance: ComplianceCheckResult | None = None,
) -> AIAssistantResponse:
    """Phase 3 – Send a tax question to the AI assistant and return the answer."""
    if not api_key:
        return AIAssistantResponse(
            answer=(
                "The AI assistant is not configured. Please set the OPENAI_API_KEY "
                "environment variable to enable this feature."
            )
        )

    context = _build_context_message(result, compliance)
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": question})

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=1024,
            temperature=0.2,
        )
        answer = response.choices[0].message.content or "No response generated."
        logger.info("AI assistant responded successfully (model=%s).", model)
        return AIAssistantResponse(answer=answer)
    except OpenAIError as exc:
        logger.error("OpenAI API error: %s", exc)
        return AIAssistantResponse(
            answer=f"The AI assistant encountered an error: {exc}. Please try again later."
        )
