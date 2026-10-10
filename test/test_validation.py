
from pydantic import ValidationError

from support_ops.models import Classification, PriorityResult


def test_invalid_sentiment_is_rejected():
    data = {
        "ticket_id": "T002",
        "intent": "withdrawal_issue",
        "urgency": "high",
        "sentiment": "happy",
        "original_language": "en",
        "translated": False,
    }

    try:
        Classification(**data)
        print("FAIL: Invalid sentiment was accepted")
    except ValidationError:
        print("PASS: Invalid sentiment rejected")


def test_incorrect_priority_score_is_rejected():
    data = {
        "ticket_id": "T003",
        "base_priority": 10,
        "customer_tier_bonus": 2,
        "funds_blocked_bonus": 5,
        "regulatory_legal_threat_bonus": 0,
        "specialist_handling_bonus": 0,
        "retrieval_weakness_bonus": 1,
        "priority_score": 99,
        "expedited": False,
        "rank": 1,
    }

    try:
        PriorityResult(**data)
        print("FAIL: Incorrect priority score was accepted")
    except ValidationError:
        print("PASS: Incorrect priority score rejected")


if __name__ == "__main__":
    test_invalid_sentiment_is_rejected()
    test_incorrect_priority_score_is_rejected()

