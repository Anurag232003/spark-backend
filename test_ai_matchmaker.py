# backend/test_ai_matchmaker.py
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from services.ai_matchmaker_service import (
    compute_compatibility_breakdown,
    generate_click_reasons,
    generate_ai_icebreaker,
    PERSONALITY_QUIZ_SCHEMA,
)

def test_compatibility_formula():
    user_doc = {
        "id": "u1",
        "name": "Anurag",
        "interests": ["Cricket", "Coding", "Gaming"],
        "relationshipGoals": "serious",
    }
    user_quiz = {
        "sunday_vibe": "gaming_home",
        "communication_style": "texting",
        "first_date": "coffee",
        "vibe": "funny",
        "relationship_intent": "serious",
    }

    cand_doc = {
        "id": "u2",
        "name": "Riya",
        "interests": ["Cricket", "Music", "Coding"],
        "relationshipGoals": "serious",
        "is_photo_verified": True,
    }
    cand_quiz = {
        "sunday_vibe": "cafe_hopping",
        "communication_style": "texting",
        "first_date": "coffee",
        "vibe": "calm",
        "relationship_intent": "serious",
    }

    breakdown = compute_compatibility_breakdown(user_doc, user_quiz, cand_doc, cand_quiz)
    print("Formula breakdown:", breakdown)
    assert 10 <= breakdown["totalScore"] <= 100, "Score out of range"
    assert breakdown["factors"]["sharedInterests"] >= 70, "Shared interests should be high"
    assert breakdown["factors"]["datingIntent"] == 100, "Dating intent exact match should be 100"

    reasons = generate_click_reasons(breakdown, cand_doc)
    print("Click reasons:", reasons)
    assert len(reasons) >= 2, "Should have at least 2 click reasons"

    icebreaker = generate_ai_icebreaker(user_doc, cand_doc, breakdown)
    print("Icebreaker:", icebreaker)
    assert len(icebreaker) > 10, "Icebreaker generated successfully"

    assert len(PERSONALITY_QUIZ_SCHEMA["questions"]) == 5, "Quiz must have 5 questions"
    print("ALL AI MATCHMAKER TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_compatibility_formula()
