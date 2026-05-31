# Copyright (c) Microsoft. All rights reserved.

from typing import Any, Dict


# Ground truth: standing knowledge-base (KB) facts + email override facts.
#
# The grader rewards an agent that surfaces BOTH the standing policy (from the
# Foundry IQ knowledge base) AND the temporary override (from Work IQ Mail):
#   - KB only            -> ~0.5 (passes policy_completeness, fails email_awareness)
#   - KB + email override -> 0.75-1.0 (passes both)
#   - No relevant content -> 0.0 (fails)
GROUND_TRUTH = {
    "hotel_budget_nyc": {
        "kb_facts": ["$250", "250/night", "250 per night"],
        "email_facts": ["$200", "200/night", "200 per night"],
        "keywords": ["marriott", "hilton", "ihg", "preferred vendor", "airbnb"],
        "email_keywords": ["budget review", "q2", "cfo", "reduced", "temporary", "override"],
    },
    "flight_business_class": {
        "kb_facts": ["VP", "vice president", "vp-level", "10 hours"],
        "email_facts": ["suspended", "premium economy", "no longer"],
        "keywords": ["business class", "approval", "delta", "5 business days"],
        "email_keywords": ["budget review", "q2", "ceo", "override", "suspended"],
    },
    "meals_domestic": {
        "kb_facts": ["$75", "75/day", "75 per day"],
        "email_facts": ["$60", "60/day", "60 per day"],
        "keywords": ["alcohol", "receipt", "25", "10 business days"],
        "email_keywords": ["budget review", "q2", "reduced", "temporary", "gsa", "suspended"],
    },
    "intl_travel_approval": {
        "kb_facts": ["VP", "vice president", "vp-level"],
        "email_facts": ["CEO", "chief executive"],
        "keywords": ["international", "approval", "security", "visa", "insurance"],
        "email_keywords": ["budget review", "q2", "changed", "override", "temporary"],
    },
}


def policy_completeness_grader(sample: Dict[str, Any], item: Dict[str, Any]) -> float:
    """Deterministic grader — scores how complete the agent's policy answer is.

    Scoring:
      1.0  = has email override facts + KB facts (KB + working email)
      0.75 = has KB facts + mentions email search (no email content found)
      0.5  = has KB facts only
      0.25 = has some keywords but no core facts
      0.0  = no relevant content
    """
    response = (sample.get("output_text") or "").lower()
    query_id = item.get("id", "")
    truth = GROUND_TRUTH.get(query_id, {})

    kb_found = False
    email_found = False
    keyword_found = False
    email_search_mentioned = False

    # Check for KB facts (e.g. $250, VP, $75)
    for fact in truth.get("kb_facts", []):
        if fact.lower() in response:
            kb_found = True
            break

    # Check for email override facts (e.g. $200, suspended, $60, CEO)
    for fact in truth.get("email_facts", []):
        if fact.lower() in response:
            email_found = True
            break

    # Check for general policy keywords
    for kw in truth.get("keywords", []):
        if kw.lower() in response:
            keyword_found = True
            break

    # Check if agent mentions searching emails (even if no results)
    email_terms = [
        "email", "mail search", "work iq", "recent communications",
        "no recent", "checking for updates", "searched",
    ]
    for term in email_terms:
        if term in response:
            email_search_mentioned = True
            break

    # Scoring
    if email_found and kb_found:
        return 1.0
    elif kb_found and email_search_mentioned:
        return 0.75
    elif kb_found and keyword_found:
        return 0.5
    elif kb_found or keyword_found:
        return 0.25
    else:
        return 0.0
