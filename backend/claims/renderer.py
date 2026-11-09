"""Safe template-based claim renderer with strict escaping and qualification labeling."""
from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from backend.claims.templates import APPROVED_TEMPLATES


class SafeClaimRenderer:
    """Renders verified and qualified claims using approved templates with HTML escaping."""

    @staticmethod
    def render(
        template_id: str,
        value: Dict[str, Any],
        status: str,
        qualification_notes: Optional[List[str]] = None,
        blocked_reasons: Optional[List[str]] = None,
    ) -> str:
        """
        Render a claim using an approved template.
        For 'blocked' claims, never returns a factual statement.
        For 'qualified' claims, prepends a qualification indicator and appends notes.
        For 'verified' claims, formats and escapes template parameters.
        """
        # Blocked claims must never render as established facts
        if status == "blocked":
            reasons = blocked_reasons or ["Verification failed."]
            safe_reasons = "; ".join([html.escape(r) for r in reasons])
            return f"[BLOCKED CLAIM] Proposal rejected by Claim Guard: {safe_reasons}"

        tmpl = APPROVED_TEMPLATES.get(template_id)
        if not tmpl:
            # Fallback if template ID is unknown or disallowed
            return f"[BLOCKED CLAIM] Template '{html.escape(template_id)}' is not in the approved Claim Guard catalog."

        format_str = tmpl["format"]
        required_params = tmpl.get("required_params", [])

        # Sanitize and HTML-escape all values passed to format
        sanitized_params: Dict[str, str] = {}
        for param in required_params:
            raw_val = value.get(param)
            if raw_val is None:
                # Missing param
                sanitized_params[param] = f"[missing {html.escape(param)}]"
            else:
                sanitized_params[param] = html.escape(str(raw_val))

        try:
            rendered = format_str.format(**sanitized_params)
        except Exception as e:
            return f"[BLOCKED CLAIM] Template rendering error: {html.escape(str(e))}"

        # If qualified, prepend clear qualification label and attach notes
        if status == "qualified":
            qual_suffix = ""
            if qualification_notes:
                notes_escaped = "; ".join([html.escape(n) for n in qualification_notes])
                qual_suffix = f" (Caveats: {notes_escaped})"
            return f"[QUALIFIED] {rendered}{qual_suffix}"

        return rendered

