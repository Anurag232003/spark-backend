# backend/services/chemistry_service.py
"""
Spark Chemistry Game Service
Interactive mini games to break the ice and build chemistry before matching or in chat.
Features 7 curated game modes:
1. Would You Rather?
2. This or That
3. Biryani vs Pizza (Food Battle)
4. Truth or Dare (Safe version)
5. Guess My Vibe
6. Rapid Fire
7. Ludo Challenge (Pre-date playful bet)

Note: Framed strictly as a fun icebreaker & vibe check, not a scientific love match.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

from database import (
    chemistry_profiles_collection,
    chemistry_sessions_collection,
    users_collection,
    matches_collection,
)

GAME_MODES: List[Dict[str, Any]] = [
    {
        "id": "WOULD_YOU_RATHER",
        "title": "Would You Rather? ⚖️",
        "tagline": "Tough & hilarious dating dilemmas",
        "icon": "Scale",
        "color": "#ff3366",
    },
    {
        "id": "THIS_OR_THAT",
        "title": "This or That 🎯",
        "tagline": "Quick binary lifestyle vibe check",
        "icon": "Sparkles",
        "color": "#784cfb",
    },
    {
        "id": "BIRYANI_VS_PIZZA",
        "title": "Biryani vs Pizza 🍕🍛",
        "tagline": "The ultimate Indian foodie showdown",
        "icon": "Utensils",
        "color": "#f59e0b",
    },
    {
        "id": "SAFE_TRUTH_OR_DARE",
        "title": "Truth or Dare 🎭",
        "tagline": "Safe, wholesome & cheeky version",
        "icon": "Smile",
        "color": "#10b981",
    },
    {
        "id": "GUESS_MY_VIBE",
        "title": "Guess My Vibe 🔮",
        "tagline": "Guess their habits & reveal the truth",
        "icon": "Eye",
        "color": "#ec4899",
    },
    {
        "id": "RAPID_FIRE",
        "title": "Rapid Fire 🔥",
        "tagline": "5 spontaneous lightning-fast questions",
        "icon": "Zap",
        "color": "#ef4444",
    },
    {
        "id": "LUDO_CHALLENGE",
        "title": "Ludo Challenge 🎲",
        "tagline": "Playful bet: Loser buys first date coffee ☕",
        "icon": "Dices",
        "color": "#3b82f6",
    },
]

# Curated question packs
QUESTION_BANK: Dict[str, List[Dict[str, Any]]] = {
    "WOULD_YOU_RATHER": [
        {
            "id": "wyr_1",
            "question": "Ideal weekend getaway plan:",
            "options": [
                {"id": "A", "text": "Mountain cabin with bonfire & chai", "emoji": "🏔️"},
                {"id": "B", "text": "Beach resort with sunset music & waves", "emoji": "🏖️"},
            ],
            "starters": {
                "A": "Since we both chose mountains & bonfire... when is our road trip? 🏔️☕",
                "B": "Sunset beach vibes for the win! Beach walk ya cafe first? 🏖️✨",
            }
        },
        {
            "id": "wyr_2",
            "question": "Would you rather have:",
            "options": [
                {"id": "A", "text": "Unlimited free artisan coffee/chai for life", "emoji": "☕"},
                {"id": "B", "text": "Free domestic flights forever", "emoji": "✈️"},
            ],
            "starters": {
                "A": "A fellow caffeine addict! What's your go-to order? ☕",
                "B": "Free flights forever! Where is our first boarding gate? ✈️🎒",
            }
        },
        {
            "id": "wyr_3",
            "question": "On a cozy Saturday night:",
            "options": [
                {"id": "A", "text": "Binge-watching thriller series with popcorn", "emoji": "🎬"},
                {"id": "B", "text": "Late night drive with a 2000s Bollywood playlist", "emoji": "🚗"},
            ],
            "starters": {
                "A": "Binge watch buddy found! What's the best series you watched recently? 🍿",
                "B": "Late night drive + Bollywood songs is pure therapy. Who controls the AUX? 🚗🎵",
            }
        },
        {
            "id": "wyr_4",
            "question": "Would you rather date someone who:",
            "options": [
                {"id": "A", "text": "Always cracks hilarious unhinged jokes", "emoji": "😂"},
                {"id": "B", "text": "Gives deep philosophical life talks at 2 AM", "emoji": "🌌"},
            ],
            "starters": {
                "A": "Humor is non-negotiable! Drop your best one-liner 😂",
                "B": "2 AM deep conversations hit different. Ready for midnight banter? 🌌",
            }
        },
        {
            "id": "wyr_5",
            "question": "First date awkward silence breaker:",
            "options": [
                {"id": "A", "text": "Spill an embarrassing childhood story", "emoji": "🙈"},
                {"id": "B", "text": "Order a weird dessert to review together", "emoji": "🍨"},
            ],
            "starters": {
                "A": "Embarrassing stories first! I promise not to laugh... too much 🙈",
                "B": "Dessert date it is! What's the weirdest food combo you secretly enjoy? 🍨",
            }
        },
    ],
    "THIS_OR_THAT": [
        {
            "id": "tot_1",
            "question": "Chai or Coffee?",
            "options": [
                {"id": "A", "text": "Desi Masala Chai", "emoji": "☕"},
                {"id": "B", "text": "Iced Vanilla Latte / Espresso", "emoji": "🥤"},
            ],
            "starters": {
                "A": "Adrak-Elaichi chai lovers unite! Tapri or aesthetic cafe? ☕",
                "B": "Iced coffee gang! Best cafe in town batao? 🥤",
            }
        },
        {
            "id": "tot_2",
            "question": "Texts or Voice Notes / Calls?",
            "options": [
                {"id": "A", "text": "Texts with memes & stickers", "emoji": "💬"},
                {"id": "B", "text": "Late-night voice notes & random calls", "emoji": "🎙️"},
            ],
            "starters": {
                "A": "Meme language is our primary love language 😂💬",
                "B": "Voice notes make conversations so much more real! Ready for a 30s audio vibe? 🎙️",
            }
        },
        {
            "id": "tot_3",
            "question": "Cats or Dogs?",
            "options": [
                {"id": "A", "text": "Playful Golden Retrievers / Dogs", "emoji": "🐶"},
                {"id": "B", "text": "Independent Mysterious Cats", "emoji": "🐱"},
            ],
            "starters": {
                "A": "Dog lover detected! If our dogs approve, it's a confirmed date 🐶",
                "B": "Cat vibes = mysterious & cozy. Show me your favorite cat meme! 🐱",
            }
        },
        {
            "id": "tot_4",
            "question": "Street Food or Fine Dine?",
            "options": [
                {"id": "A", "text": "Street chaat, momos & rolls", "emoji": "🌮"},
                {"id": "B", "text": "Dim lighting & rooftop aesthetics", "emoji": "🍷"},
            ],
            "starters": {
                "A": "Street food over fancy restaurants any day! Gol gappe ya momos pehle? 🌮",
                "B": "Rooftop ambiance with good music is unbeatable! 🍷✨",
            }
        },
        {
            "id": "tot_5",
            "question": "Early Morning Sunrise or 2 AM Night Owl?",
            "options": [
                {"id": "A", "text": "Early morning run & fresh breeze", "emoji": "🌅"},
                {"id": "B", "text": "2 AM deep thoughts & silence", "emoji": "🌙"},
            ],
            "starters": {
                "A": "Morning people have their life together! What time do you wake up? 🌅",
                "B": "Fellow night owl! Why are the best conversations always after midnight? 🌙",
            }
        },
    ],
    "BIRYANI_VS_PIZZA": [
        {
            "id": "bvp_1",
            "question": "Friday Night Comfort Food:",
            "options": [
                {"id": "A", "text": "Aromatic Hyderabadi Dum Biryani + Raita", "emoji": "🍛"},
                {"id": "B", "text": "Hot Cheesy Sourdough Pizza + Garlic Dip", "emoji": "🍕"},
            ],
            "starters": {
                "A": "Biryani is emotion, not just food! Mirchi ka salan yes or no? 🍛",
                "B": "Extra cheese pizza lovers! What's your verdict on pineapple on pizza? 🍕",
            }
        },
        {
            "id": "bvp_2",
            "question": "Evening 5 PM Snack Fix:",
            "options": [
                {"id": "A", "text": "Steaming Kurkure / Tandoori Momos", "emoji": "🥟"},
                {"id": "B", "text": "Creamy White Sauce Penne Pasta", "emoji": "🍝"},
            ],
            "starters": {
                "A": "Momo lovers forever! Spicy red chutney handler or mayo? 🥟🔥",
                "B": "Cheesy pasta date! Extra parmesan or spicy chilli flakes? 🍝",
            }
        },
        {
            "id": "bvp_3",
            "question": "Sweet Tooth Craving:",
            "options": [
                {"id": "A", "text": "Warm Gulab Jamun with Vanilla Ice Cream", "emoji": "🍨"},
                {"id": "B", "text": "Warm Belgian Chocolate Waffle / Brownie", "emoji": "🧇"},
            ],
            "starters": {
                "A": "Warm gulab jamun + cold vanilla ice cream is culinary perfection! 🍨",
                "B": "Belgian chocolate waffle gang! Let's hit the waffle parlor? 🧇",
            }
        },
        {
            "id": "bvp_4",
            "question": "The Ultimate Chaat Championship:",
            "options": [
                {"id": "A", "text": "Crispy Pani Puri / Gol Gappe (Teekha Pani)", "emoji": "🥣"},
                {"id": "B", "text": "Crispy Dahi Bhalla / Papdi Chaat", "emoji": "🥔"},
            ],
            "starters": {
                "A": "Teekha gol gappe challenge! How many can you eat in one round? 🥣🔥",
                "B": "Dahi papdi chaat has the perfect crunch-to-sweet ratio! 🥔",
            }
        },
        {
            "id": "bvp_5",
            "question": "Late Night 1 AM Food Run:",
            "options": [
                {"id": "A", "text": "Butter Chicken / Paneer Tikka Kathi Roll", "emoji": "🌯"},
                {"id": "B", "text": "Loaded Cheese Burger & Curly Fries", "emoji": "🍔"},
            ],
            "starters": {
                "A": "Midnight kathi roll runs are legendary! Egg roll or paneer tikka? 🌯",
                "B": "Midnight burger run! Who's driving? 🍔🚗",
            }
        },
    ],
    "SAFE_TRUTH_OR_DARE": [
        {
            "id": "std_1",
            "question": "Safe Truth: Your weirdest food habit:",
            "options": [
                {"id": "A", "text": "Dipping biscuits/chips in unusual drinks/gravy", "emoji": "🍪"},
                {"id": "B", "text": "Mixing sweet & spicy in totally bizarre ways", "emoji": "🌶️"},
            ],
            "starters": {
                "A": "Spill the tea! What's the weirdest thing you dipped in chai? 🍪☕",
                "B": "Sweet and spicy combinations can be genius or criminal. Which one are you? 🌶️",
            }
        },
        {
            "id": "std_2",
            "question": "Safe Dare: How would you open a chat?",
            "options": [
                {"id": "A", "text": "Send a voice note mimicking a famous Bollywood hero", "emoji": "🎙️"},
                {"id": "B", "text": "Describe your ideal first date using ONLY 3 emojis", "emoji": "✨"},
            ],
            "starters": {
                "A": "A Bollywood voice note? I'm holding you to this dare! 😂🎙️",
                "B": "Okay, challenge accepted: Here are my 3 emojis ☕🚗🌙. Your turn! ✨",
            }
        },
        {
            "id": "std_3",
            "question": "Safe Truth: What song do you blast in private?",
            "options": [
                {"id": "A", "text": "Cheesy 90s Bollywood dance anthems", "emoji": "💃"},
                {"id": "B", "text": "Nostalgic 2010s English pop / Punjabi bangers", "emoji": "🎧"},
            ],
            "starters": {
                "A": "90s Bollywood tracks have the best energy! What's on top of your playlist? 💃",
                "B": "Punjabi bangers & pop nostalgia! Spotify blend test karein? 🎧",
            }
        },
        {
            "id": "std_4",
            "question": "Safe Dare: What's your best quick party trick?",
            "options": [
                {"id": "A", "text": "Guessing someone's astrological vibe or zodiac", "emoji": "🔮"},
                {"id": "B", "text": "Remembering useless pop culture trivia & movie quotes", "emoji": "🎬"},
            ],
            "starters": {
                "A": "Guess my vibe/zodiac! Let's see how accurate you are 🔮",
                "B": "Pop culture trivia duel! Give me your hardest movie quote 🎬",
            }
        },
        {
            "id": "std_5",
            "question": "Safe Truth: The most cringe thing you did to impress someone:",
            "options": [
                {"id": "A", "text": "Pretended to love their favorite boring band/sport", "emoji": "🎸"},
                {"id": "B", "text": "Accidentally liked a 5-year-old Instagram photo", "emoji": "📱"},
            ],
            "starters": {
                "A": "Faking interest in a band is peak romance struggle! What band was it? 🎸😂",
                "B": "The horror of the deep-scroll accidental like! We've all been there 📱🙈",
            }
        },
    ],
    "GUESS_MY_VIBE": [
        {
            "id": "gmv_1",
            "question": "How do I usually spend Sunday afternoon?",
            "options": [
                {"id": "A", "text": "Exploring a new cafe or shopping street", "emoji": "☕"},
                {"id": "B", "text": "Sleeping in & cozy blanket Netflix marathon", "emoji": "🛋️"},
            ],
            "starters": {
                "A": "Cafe exploration on Sundays is elite. What's your favorite spot in town? ☕",
                "B": "Sunday hibernation mode! What shows are currently on your watchlist? 🛋️",
            }
        },
        {
            "id": "gmv_2",
            "question": "When travel plans get made, I am the one who:",
            "options": [
                {"id": "A", "text": "Has a full itinerary with maps & cafe bookings", "emoji": "🗺️"},
                {"id": "B", "text": "Packs 2 hours before & goes totally with the flow", "emoji": "🎒"},
            ],
            "starters": {
                "A": "The organized planner! Every spontaneous traveler needs one of you 🗺️",
                "B": "Spontaneous backpacker! Last-minute trips always make the best memories 🎒",
            }
        },
        {
            "id": "gmv_3",
            "question": "My comfort social setting:",
            "options": [
                {"id": "A", "text": "Small group of 3-4 close friends laughing over snacks", "emoji": "👥"},
                {"id": "B", "text": "High energy club / concert singing at top of lungs", "emoji": "🪩"},
            ],
            "starters": {
                "A": "Intimate cozy hangouts > crowded loud clubs any day! 👥✨",
                "B": "Concert & party energy! Who was the last artist you saw live? 🪩",
            }
        },
        {
            "id": "gmv_4",
            "question": "If we won a ₹50,000 shopping spree right now:",
            "options": [
                {"id": "A", "text": "Sneakers, fashion & aesthetic room decor", "emoji": "👟"},
                {"id": "B", "text": "Book tickets for a spontaneous trip this weekend", "emoji": "🎫"},
            ],
            "starters": {
                "A": "Sneakers & aesthetics! What's on your wishlist right now? 👟",
                "B": "Tickets booked! Where are we flying this weekend? 🎫✈️",
            }
        },
        {
            "id": "gmv_5",
            "question": "On the first date, what is most important?",
            "options": [
                {"id": "A", "text": "Effortless conversation where time flies without checking phones", "emoji": "⏳"},
                {"id": "B", "text": "Shared sense of humor and laughing until our stomachs hurt", "emoji": "😂"},
            ],
            "starters": {
                "A": "Time flying without checking phones is the ultimate green flag ⏳💚",
                "B": "Laughing until stomachs hurt = best first date formula! 😂",
            }
        },
    ],
    "RAPID_FIRE": [
        {
            "id": "rf_1",
            "question": "Tea time partner:",
            "options": [
                {"id": "A", "text": "Parle-G or Rusk", "emoji": "🍪"},
                {"id": "B", "text": "Samosa or Kachori", "emoji": "🥟"},
            ],
            "starters": {
                "A": "Classic Parle-G dip! The 3-second rule is high stakes 🍪",
                "B": "Samosa + Chai = undisputed GOAT combo! 🥟☕",
            }
        },
        {
            "id": "rf_2",
            "question": "Movie choice:",
            "options": [
                {"id": "A", "text": "Psychological Thriller / Murder Mystery", "emoji": "🕵️"},
                {"id": "B", "text": "Warm Feel-good Romance / Comedy", "emoji": "💖"},
            ],
            "starters": {
                "A": "Thrillee fans notice every clue! Favorite mind-bending movie? 🕵️",
                "B": "Feel-good comfort movies! What movie can you rewatch 10 times? 💖",
            }
        },
        {
            "id": "rf_3",
            "question": "Spicy Food Tolerance:",
            "options": [
                {"id": "A", "text": "Can handle extra green chillies like a champion", "emoji": "🌶️🔥"},
                {"id": "B", "text": "Mild spice with sweet lassi on standby", "emoji": "🥛"},
            ],
            "starters": {
                "A": "Spicy food champion! Let's test this over street chaat 🌶️🔥",
                "B": "Mild spice gang! I'll make sure the lassi is ready on our date 🥛",
            }
        },
        {
            "id": "rf_4",
            "question": "When getting ready for an event:",
            "options": [
                {"id": "A", "text": "Ready in 15 minutes flat", "emoji": "⚡"},
                {"id": "B", "text": "Takes 1 hour + full concert performance in mirror", "emoji": "🪞"},
            ],
            "starters": {
                "A": "15 minutes flat? That's superhuman speed! ⚡",
                "B": "Mirror concerts are mandatory for outfit confidence! What song was playing? 🪞🎶",
            }
        },
        {
            "id": "rf_5",
            "question": "Go-to First Date activity:",
            "options": [
                {"id": "A", "text": "Coffee & chill walk in a park/market", "emoji": "☕🚶"},
                {"id": "B", "text": "Arcade gaming, bowling or board games", "emoji": "🎳🎯"},
            ],
            "starters": {
                "A": "Coffee + 20 minute walk is the cleanest, lowest-pressure date ever ☕🚶",
                "B": "Arcade & bowling! Let's see who has better aim 🎳🎯",
            }
        },
    ],
    "LUDO_CHALLENGE": [
        {
            "id": "lc_1",
            "question": "The Pre-Date Bet: If I beat you in a quick game:",
            "options": [
                {"id": "A", "text": "You buy the first round of artisanal coffee ☕", "emoji": "☕"},
                {"id": "B", "text": "You treat me to the best street momos in town 🥟", "emoji": "🥟"},
            ],
            "starters": {
                "A": "Bet accepted! Coffee date stakes are officially on ☕🎲",
                "B": "Momo stakes! Prepare to buy me a plate when I win 🥟🎲",
            }
        },
        {
            "id": "lc_2",
            "question": "Your Ludo / Board Game Strategy:",
            "options": [
                {"id": "A", "text": "Aggressive hunter — I cut every token in sight", "emoji": "⚔️"},
                {"id": "B", "text": "Peaceful pacifist — I quietly sprint to safety", "emoji": "🛡️"},
            ],
            "starters": {
                "A": "Aggressive token hunter! No mercy on the board? 😂⚔️",
                "B": "Peaceful strategy works until a 6 rolls! Let's see your luck 🎲",
            }
        },
        {
            "id": "lc_3",
            "question": "If you roll three 6s in a row:",
            "options": [
                {"id": "A", "text": "Celebration dance around the room", "emoji": "🕺"},
                {"id": "B", "text": "Cry because turn gets cancelled", "emoji": "😭"},
            ],
            "starters": {
                "A": "Celebration dance is mandatory! Show me your winning moves 🕺",
                "B": "Three 6s curse is heartbreak! Have you had that happen? 😭",
            }
        },
        {
            "id": "lc_4",
            "question": "What is your lucky token color?",
            "options": [
                {"id": "A", "text": "Fiery Red or Sunny Yellow", "emoji": "🔴🟡"},
                {"id": "B", "text": "Cool Blue or Lucky Green", "emoji": "🔵🟢"},
            ],
            "starters": {
                "A": "Red & Yellow energy! You take Red, I take Yellow? 🔴🟡",
                "B": "Blue & Green squad! Ready for a friendly showdown? 🔵🟢",
            }
        },
        {
            "id": "lc_5",
            "question": "After the game, the loser must:",
            "options": [
                {"id": "A", "text": "Plan the entire first date itinerary", "emoji": "📋"},
                {"id": "B", "text": "Send a goofy victory selfie to the winner", "emoji": "🤳"},
            ],
            "starters": {
                "A": "Loser plans the date? Deal! I hope you have good cafe recommendations 📋✨",
                "B": "Goofy victory selfie bet accepted! Get your camera ready 🤳😂",
            }
        },
    ],
}


def get_game_modes() -> List[Dict[str, Any]]:
    """Returns metadata for all available game modes."""
    return GAME_MODES


def get_game_questions(mode: str, count: int = 5) -> List[Dict[str, Any]]:
    """Returns a list of questions for the selected mode."""
    mode_clean = mode.strip().upper()
    questions = QUESTION_BANK.get(mode_clean, QUESTION_BANK["WOULD_YOU_RATHER"])
    return questions[:count]


def save_user_vibe_profile(user_id: str, answers: Dict[str, str]) -> Dict[str, Any]:
    """
    Saves or updates user's baseline chemistry vibe answers.
    Answers format: {"tot_1": "A", "bvp_1": "B", ...}
    """
    chemistry_profiles_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "answers": answers,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True
    )
    return {"status": "SUCCESS", "message": "Chemistry vibe profile updated!"}


def get_user_vibe_profile(user_id: str) -> Dict[str, Any]:
    """Retrieves user's saved chemistry vibe profile."""
    profile = chemistry_profiles_collection.find_one({"user_id": user_id})
    if not profile:
        return {"hasProfile": False, "answers": {}}
    return {
        "hasProfile": True,
        "answers": profile.get("answers", {}),
        "updatedAt": profile.get("updated_at", datetime.utcnow()).isoformat() if profile.get("updated_at") else None,
    }


def compare_chemistry(
    user_id: str,
    target_user_id: str,
    mode: str,
    my_answers: Dict[str, str]
) -> Dict[str, Any]:
    """
    Compares user's answers against target user's answers (or fallback simulated match).
    Calculates vibe alignment, shared picks, and unlocks 2 tailored conversation starters.
    
    IMPORTANT: Includes explicit disclaimer stating this is a fun icebreaker, not a scientific love match.
    """
    mode_clean = mode.strip().upper()
    questions = QUESTION_BANK.get(mode_clean, QUESTION_BANK["WOULD_YOU_RATHER"])
    
    # Check target user's saved vibe answers
    target_profile = chemistry_profiles_collection.find_one({"user_id": target_user_id})
    target_answers = target_profile.get("answers", {}) if target_profile else {}
    
    target_user = users_collection.find_one({"id": target_user_id}) or {}
    target_name = target_user.get("name", "them")

    # If target has not answered this specific question set, generate realistic baseline comparison
    shared_picks = []
    unlocked_starters = []
    match_count = 0
    total_compared = 0

    for q in questions:
        q_id = q["id"]
        my_choice = my_answers.get(q_id)
        if not my_choice:
            continue
        
        total_compared += 1
        
        # Determine target's choice
        if q_id in target_answers:
            target_choice = target_answers[q_id]
        else:
            # Deterministic pseudo-random choice based on hash so it stays consistent per pair
            seed = hash(f"{target_user_id}_{q_id}")
            target_choice = "A" if (seed % 3 != 0) else "B"

        is_match = (my_choice == target_choice)
        if is_match:
            match_count += 1
            # Find matching option text
            opt_obj = next((o for o in q["options"] if o["id"] == my_choice), None)
            if opt_obj:
                shared_picks.append({
                    "question": q["question"],
                    "choice": opt_obj["text"],
                    "emoji": opt_obj["emoji"],
                })
            # Add tailor-made starter
            if "starters" in q and my_choice in q["starters"]:
                unlocked_starters.append(q["starters"][my_choice])

    if total_compared == 0:
        total_compared = len(questions)
        match_count = max(2, total_compared - 1)

    # Compute Vibe Match percentage (capped nicely between 65% and 95% for fun positive reinforcement)
    raw_ratio = match_count / max(1, total_compared)
    vibe_percentage = int(min(98, max(65, raw_ratio * 100)))

    # Guarantee at least 2 fun conversation starters
    if len(unlocked_starters) < 2:
        fallback_starters = [
            f"We took the {mode_clean.replace('_', ' ').title()} challenge! When are we settling our picks over coffee? ☕",
            f"Our Chemistry vibe check gave us {vibe_percentage}%! Street food or cafe date first? 😂",
            f"I see we have matching taste in weekend plans! Gol gappe ya momos pehle? 🌮",
        ]
        for fb in fallback_starters:
            if fb not in unlocked_starters:
                unlocked_starters.append(fb)
            if len(unlocked_starters) >= 2:
                break

    return {
        "status": "SUCCESS",
        "mode": mode_clean,
        "vibeScore": vibe_percentage,
        "matchCount": match_count,
        "totalCompared": total_compared,
        "sharedPicks": shared_picks,
        "unlockedStarters": unlocked_starters[:3],
        "disclaimer": "✨ Fun Vibe Check only • Not a guaranteed compatibility score",
        "targetName": target_name,
    }


def create_chat_game_challenge(match_id: str, sender_id: str, mode: str) -> Dict[str, Any]:
    """
    Creates an in-chat interactive Chemistry Challenge session.
    Broadcasted to the match participants so both can answer and see mutual results.
    """
    mode_clean = mode.strip().upper()
    session_id = f"chem-{uuid.uuid4().hex[:12]}"
    
    questions = get_game_questions(mode_clean, count=5)
    
    session_doc = {
        "session_id": session_id,
        "match_id": match_id,
        "challenger_id": sender_id,
        "mode": mode_clean,
        "status": "PENDING",  # PENDING, IN_PROGRESS, COMPLETED
        "answers": {
            sender_id: {},
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    chemistry_sessions_collection.insert_one(session_doc)
    
    return {
        "sessionId": session_id,
        "matchId": match_id,
        "mode": mode_clean,
        "challengerId": sender_id,
        "questions": questions,
        "status": "PENDING"
    }


def submit_chat_game_answers(session_id: str, user_id: str, answers: Dict[str, str]) -> Dict[str, Any]:
    """
    Submits user's answers for an active in-chat chemistry session.
    If both match participants have answered, computes results and marks COMPLETED.
    """
    session = chemistry_sessions_collection.find_one({"session_id": session_id})
    if not session:
        raise ValueError("Chemistry challenge session not found.")

    answers_dict = session.get("answers", {})
    answers_dict[user_id] = answers

    # Check match doc to find participants
    match = matches_collection.find_one({"_id": ObjectId(session["match_id"])}) or {}
    participants = match.get("participants", [match.get("user1_id"), match.get("user2_id")])
    participants = [p for p in participants if p]

    all_answered = len(participants) > 0 and all(p in answers_dict and len(answers_dict[p]) > 0 for p in participants)

    update_fields: Dict[str, Any] = {
        f"answers.{user_id}": answers,
        "updated_at": datetime.utcnow(),
    }
    
    results = None
    if all_answered or len(answers_dict) >= 2:
        update_fields["status"] = "COMPLETED"
        # Compare first two participants
        p_keys = list(answers_dict.keys())
        p1, p2 = p_keys[0], p_keys[1]
        results = compare_chemistry(p1, p2, session["mode"], answers_dict[p1])
        update_fields["results"] = results

    chemistry_sessions_collection.update_one(
        {"session_id": session_id},
        {"$set": update_fields}
    )

    updated = chemistry_sessions_collection.find_one({"session_id": session_id}) or {}
    
    return {
        "sessionId": session_id,
        "status": updated.get("status", "IN_PROGRESS"),
        "results": results or updated.get("results"),
        "hasAnswered": True,
    }
