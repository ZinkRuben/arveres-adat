#!/usr/bin/env python3
"""
MBVK Ownership Share Parser & Normalizer
Converts messy Hungarian bailiff ownership strings (e.g. '1/2 + 1/2 (1/1)', '1/2+1/2=1/1',
'2/2', 'mindösszesen 1/1', '1/1-ed') into exact numeric fractions and percentages.
"""

import re
from fractions import Fraction


def parse_ownership_share(raw):
    """
    Parses a Hungarian bailiff ownership string.
    Returns:
        tuple: (fraction_float, percentage_str, is_full_ownership, parse_category, explanation)
    """
    if not raw or not raw.strip():
        return None, None, False, "empty", "Empty string"

    s = raw.strip()

    # 1. Explicit text meaning full ownership
    if re.search(r"(mindösszesen|összesen)\s*1/1", s, re.I):
        return 1.0, "100.0%", True, "text_annotated", "Explicit total 1/1"

    # Separate parenthesized notes to avoid double-counting
    # e.g. '1/2 + 1/2 (1/1)' -> outside='1/2 + 1/2', inside='1/1'
    # e.g. '1/1 (1/2+1/2)' -> outside='1/1', inside='1/2+1/2'
    inside_paren = None
    m_paren = re.search(r"\((.*?)\)", s)
    if m_paren:
        inside_paren = m_paren.group(1).strip()
        s_outside = re.sub(r"\s*\([^\)]*\)", "", s).strip()
    else:
        # Check for unclosed parenthesis due to database length truncation (e.g. '1/1 (33/100...')
        if "(" in s:
            s_outside = s.split("(")[0].strip()
            inside_paren = s.split("(")[1].strip()
        else:
            s_outside = s

    # Primary string to parse is the outside part (or inside if outside is empty)
    target_str = s_outside if s_outside else inside_paren

    # 2. Check for '=' in target_str (e.g. '1/2+1/2=1/1', '2/4=1/1', '100/358+79/358=179/3')
    if "=" in target_str:
        parts = target_str.split("=")
        lhs, rhs = parts[0].strip(), parts[-1].strip()

        # Check RHS: is it a valid clean fraction?
        m_rhs = re.match(r"^(\d+)\s*/\s*(\d+)$", rhs)
        if m_rhs:
            num, den = int(m_rhs.group(1)), int(m_rhs.group(2))
            # Verify denominator is not truncated (e.g. /3 when LHS is /358)
            lhs_denoms = re.findall(r"/\s*(\d+)", lhs)
            if not lhs_denoms or den in [int(d) for d in lhs_denoms] or den in (1, 2, 4, 8, 10, 100):
                val = float(num / den)
                is_full = abs(val - 1.0) < 1e-5
                return val, f"{val*100:.1f}%", is_full, "equation_rhs", f"Parsed RHS of = ({num}/{den})"

        # Otherwise evaluate LHS
        lhs_fracs = re.findall(r"(\d+)\s*/\s*(\d+)", lhs)
        if lhs_fracs:
            tot = sum(Fraction(int(n), int(d)) for n, d in lhs_fracs)
            val = float(tot)
            is_full = abs(val - 1.0) < 1e-5
            return val, f"{val*100:.1f}%", is_full, "equation_lhs", "Summed LHS of ="

    # 3. Simple clean fraction (e.g. '1/2', '1/1', '2/2', '3/4', '12/48')
    m_simple = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*(?:-(?:ed|ad|od|üd))?\s*$", target_str)
    if m_simple:
        num, den = int(m_simple.group(1)), int(m_simple.group(2))
        if den > 0:
            val = float(num / den)
            is_full = abs(val - 1.0) < 1e-5
            return val, f"{val*100:.1f}%", is_full, "standard_fraction", f"Single fraction {num}/{den}"

    # 4. Check for sum of fractions (e.g. '1/2 + 1/2', '1/2-1/2', '96/672+192/672+96/67')
    frac_matches = list(re.finditer(r"(\d+)\s*/\s*(\d+)", target_str))
    if frac_matches:
        # Check and repair 20-character database length truncations where denominators share a prefix
        repaired_fracs = []
        first_denom = None
        for i, m in enumerate(frac_matches):
            n, d = int(m.group(1)), m.group(2)
            if i == 0:
                first_denom = d
                repaired_fracs.append((n, int(d)))
            else:
                # If d is a truncated prefix of first_denom (e.g. '67' vs '672', '288' vs '2881', '1' vs '100000')
                if first_denom and first_denom.startswith(d) and len(d) < len(first_denom) and len(target_str) >= 19:
                    repaired_fracs.append((n, int(first_denom)))
                else:
                    repaired_fracs.append((n, int(d)))

        if len(repaired_fracs) > 1:
            tot = sum(Fraction(n, d) for n, d in repaired_fracs)
            val = float(tot)
            is_full = abs(val - 1.0) < 1e-5
            return val, f"{val*100:.1f}%", is_full, "fraction_sum", f"Sum of {len(repaired_fracs)} fractions"
        elif len(repaired_fracs) == 1:
            n, d = repaired_fracs[0]
            val = float(n / d)
            is_full = abs(val - 1.0) < 1e-5
            return val, f"{val*100:.1f}%", is_full, "single_fraction", f"{n}/{d}"

    # 5. Check inside_paren as fallback if it contains a single fraction
    if inside_paren:
        m_in = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", inside_paren)
        if m_in:
            num, den = int(m_in.group(1)), int(m_in.group(2))
            if den > 0:
                val = float(num / den)
                is_full = abs(val - 1.0) < 1e-5
                return val, f"{val*100:.1f}%", is_full, "inside_parenthesis_fallback", f"{num}/{den}"

    # 6. Negative fraction typo (e.g. '-1/4')
    m_neg = re.match(r"^\s*-\s*(\d+)\s*/\s*(\d+)", target_str)
    if m_neg:
        num, den = int(m_neg.group(1)), int(m_neg.group(2))
        if den > 0:
            val = float(num / den)
            return val, f"{val*100:.1f}%", False, "negative_typo_fixed", f"Corrected minus typo {num}/{den}"

    return None, None, False, "unparseable", f"Unparseable string: {s}"
