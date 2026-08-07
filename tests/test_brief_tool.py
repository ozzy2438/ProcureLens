from procurelens.agent.tools.brief_tool import DRAFT_BANNER, BidBriefTool


def test_brief_is_draft_grounded_and_deterministic():
    tender = {
        "tender_id": "ATM-42",
        "tender_title": "Responsible AI advisory",
        "agency": "Department of Finance",
        "estimated_value_aud": 750_000,
        "procurement_method": "open",
        "close_date": "2026-09-01",
    }
    ml_result = {
        "fit_score": {
            "score": 82,
            "fit_band": "strong_fit",
            "positive_reasons": ["AI capability match"],
            "negative_reasons": ["New agency relationship"],
            "scorer_version": "1.0.0",
        },
        "amendment_risk": {
            "probability": 0.2,
            "risk_band": "medium",
            "model_version": "3",
        },
    }
    rag_result = {
        "answer": "Value for money includes non-price factors.",
        "sources": [
            {
                "document": "Commonwealth Procurement Rules — 17 November 2025",
                "page": 12,
                "url": "https://www.finance.gov.au/cpr.pdf",
                "section": "Value for money",
            }
        ],
    }
    tool = BidBriefTool()
    first = tool.compose(tender=tender, ml_result=ml_result, rag_result=rag_result)
    second = tool.compose(tender=tender, ml_result=ml_result, rag_result=rag_result)

    assert first == second
    assert first.markdown.count(DRAFT_BANNER) == 2
    assert first.recommendation == "BID"
    assert "p. 12" in first.markdown
