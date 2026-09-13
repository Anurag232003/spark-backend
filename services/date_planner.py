"""
Spark Date Planner Service — Match to Real-World Date Engine.
Provides:
1. Contextual Date Itineraries (Budget + Activity + Mutual Interests & Locations)
2. Gemini AI layer + Instant Smart Fallback Templates
3. Date Proposal payload structures and status tracking (PENDING, ACCEPTED, DECLINED)
4. Calendar Event generator metadata (Google Calendar & iCal formats)
"""

import os
import json
import uuid
import random
import urllib.request
from typing import List, Dict, Optional, Any
from datetime import datetime

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# ==============================================================================
# 1. SMART CURATED LOCAL DATE ITINERARY TEMPLATES
# ==============================================================================

DATE_TEMPLATES = {
    "coffee": {
        "300": [
            {
                "title": "Cozy Local Cafe & Cold Brews ☕",
                "vibe": "Low Pressure & Authentic",
                "estimatedBudget": "₹300",
                "duration": "1 Hour",
                "description": "Meet at a quiet neighborhood cafe for iced cold brews or artisan lattes. Perfect low-pressure setting to break the ice.",
                "highlights": ["Comfortable quiet seating", "Low commitment", "Easy conversation flow"]
            },
            {
                "title": "Coffee & Book Browse Stroll 📖☕",
                "vibe": "Intellectual & Relaxed",
                "estimatedBudget": "₹300",
                "duration": "1 - 1.5 Hours",
                "description": "Grab takeaway coffees and wander through a local indie bookstore or quiet street market nearby.",
                "highlights": ["Zero awkward silences", "Natural conversation triggers", "Very relaxed vibe"]
            }
        ],
        "500": [
            {
                "title": "Specialty Roastery & Pastry Tasting 🥐☕",
                "vibe": "Chill & Refined",
                "estimatedBudget": "₹500",
                "duration": "1.5 Hours",
                "description": "Visit a modern specialty coffee roaster (like Blue Tokai / Third Wave style) for pour-overs and a warm almond croissant.",
                "highlights": ["Aesthetic ambiance", "Delicious artisanal brew", "Great photo-worthy corner"]
            },
            {
                "title": "Aesthetic Cafe + 20-min Walk 🌿☕",
                "vibe": "Breezy & Conversational",
                "estimatedBudget": "₹500",
                "duration": "1.5 Hours",
                "description": "Sit down for coffee and light bites, followed by an easy 20-minute walk in a nearby shaded park or avenue.",
                "highlights": ["Dynamic energy shift", "Great movement", "Romantic without being intense"]
            }
        ],
        "1000": [
            {
                "title": "Artisanal Coffee Flights & Gourmet Desserts 🍰☕",
                "vibe": "Premium & Indulgent",
                "estimatedBudget": "₹1000",
                "duration": "2 Hours",
                "description": "Experience curated coffee tasting flights paired with signature cheesecake or tiramisu in a high-end botanical cafe.",
                "highlights": ["Luxurious calm setting", "Gourmet experience", "Memorable first impression"]
            }
        ]
    },
    "walk": {
        "300": [
            {
                "title": "Sunset Promenade & Gelato Stroll 🍦🌅",
                "vibe": "Romantic & Effortless",
                "estimatedBudget": "₹300",
                "duration": "1 - 1.5 Hours",
                "description": "Meet just before sunset for a refreshing stroll along the lake/promenade/park, with artisanal gelato on the go.",
                "highlights": ["Golden hour lighting", "Fresh air", "Relaxed pacing"]
            },
            {
                "title": "Heritage Lane & Street Chai Walk ☕🏛️",
                "vibe": "Cultural & Nostalgic",
                "estimatedBudget": "₹250",
                "duration": "1.5 Hours",
                "description": "Explore an old historic district or artsy quarter at golden hour, stopping by a vintage tea spot.",
                "highlights": ["Vibrant architecture", "Great storytelling prompts", "Casual comfort"]
            }
        ],
        "500": [
            {
                "title": "Botanical Garden Walk & Iced Teas 🌿🍹",
                "vibe": "Peaceful & Scenic",
                "estimatedBudget": "₹500",
                "duration": "2 Hours",
                "description": "Walk through lush botanical gardens or a heritage park with refreshing iced matcha or herbal drinks in hand.",
                "highlights": ["Scenic green backdrop", "Serene quietude", "Easy walking rhythm"]
            }
        ],
        "1000": [
            {
                "title": "Curated Art District Walk & Rooftop Sunset 🎨🌆",
                "vibe": "Classy & Inspiring",
                "estimatedBudget": "₹1000",
                "duration": "2.5 Hours",
                "description": "Browse an open gallery or arts precinct, culminating in refreshing mocktails/beverages on a rooftop terrace.",
                "highlights": ["Sophisticated setting", "Panoramic views", "High aesthetic value"]
            }
        ]
    },
    "gaming": {
        "300": [
            {
                "title": "Board Games & Cafe Friendly Match 🎲☕",
                "vibe": "Playful & Interactive",
                "estimatedBudget": "₹300",
                "duration": "1.5 Hours",
                "description": "Meet at a cozy board-game friendly cafe for a quick game of Codenames, Uno, or Jenga over iced drinks.",
                "highlights": ["Breaks the ice instantly", "Shows playful personality", "Lots of genuine laughs"]
            }
        ],
        "500": [
            {
                "title": "Arcade Air Hockey & Retro Games 🕹️🎟️",
                "vibe": "Fun & Nostalgic",
                "estimatedBudget": "₹500",
                "duration": "1.5 - 2 Hours",
                "description": "Head to a bowling alley or modern arcade for 1v1 air hockey, basketball shootouts, and light competitive banter.",
                "highlights": ["High energy fun", "Healthy competitive spark", "No awkward dinner pauses"]
            }
        ],
        "1000": [
            {
                "title": "Bowling Match & Sliders Lounge 🎳🍔",
                "vibe": "Vibrant & Dynamic",
                "estimatedBudget": "₹1000",
                "duration": "2 Hours",
                "description": "Two rounds of bowling with music, gourmet sliders, and drinks. The loser buys dessert afterwards!",
                "highlights": ["Engaging friendly rivalry", "Lively social scene", "Natural celebrations and high-fives"]
            }
        ]
    },
    "movie": {
        "300": [
            {
                "title": "Matinee Screening & Theater Popcorn 🍿🎬",
                "vibe": "Classic & Low Key",
                "estimatedBudget": "₹300",
                "duration": "2.5 Hours",
                "description": "Catch a daytime or early evening screening of a compelling new indie release with shared warm popcorn.",
                "highlights": ["Shared cultural experience", "No small-talk pressure during film", "Great post-movie discussion"]
            }
        ],
        "500": [
            {
                "title": "Cinema Screening & Coffee Debrief ☕🎬",
                "vibe": "Classic Romance",
                "estimatedBudget": "₹500",
                "duration": "3 Hours",
                "description": "Watch a critically acclaimed movie together, followed by a 20-minute coffee stop nearby to debate the ending.",
                "highlights": ["Seamless 2-part date", "Built-in conversation topic", "Comfortable shared time"]
            }
        ],
        "1000": [
            {
                "title": "IMAX Experience & Post-Movie Dessert Lounge 🍨🎞️",
                "vibe": "Immersive & Premium",
                "estimatedBudget": "₹1000",
                "duration": "3.5 Hours",
                "description": "Premium large-format screening with plush seating, followed by an intimate dessert cafe to talk about thoughts on the story.",
                "highlights": ["Top tier comfort", "Feels like a special event", "Quality time"]
            }
        ]
    },
    "food": {
        "300": [
            {
                "title": "Signature Street Food Trail & Kulhad Chai 🍲☕",
                "vibe": "Flavorful & Unpretentious",
                "estimatedBudget": "₹300",
                "duration": "1.5 Hours",
                "description": "Sample the city's most beloved authentic bites together, finishing with hot kulhad chai in the evening breeze.",
                "highlights": ["True comfort food", "Spontaneous fun", "Great authentic vibe"]
            }
        ],
        "500": [
            {
                "title": "Woodfired Pizza Slice & Craft Shakes 🍕🥤",
                "vibe": "Casual & Comforting",
                "estimatedBudget": "₹500",
                "duration": "1.5 Hours",
                "description": "Grab fresh sourdough pizza slices and thick milkshakes at an upbeat casual pizzeria.",
                "highlights": ["Delicious shared food", "Relaxed informal seating", "Easy to connect"]
            }
        ],
        "1000": [
            {
                "title": "Intimate Corner Bistro & Pasta Evening 🍝🕯️",
                "vibe": "Romantic & Sophisticated",
                "estimatedBudget": "₹1000",
                "duration": "2 Hours",
                "description": "A candle-lit corner table at a stylish Italian or pan-Asian bistro with handmade pasta and mocktails/wine.",
                "highlights": ["Romantic mood lighting", "Exceptional food presentation", "True adult date experience"]
            }
        ]
    }
}


# ==============================================================================
# 2. GEMINI AI ENGINE (TAILORED DATE PROPOSALS)
# ==============================================================================

async def call_gemini_date_planner(prompt: str) -> Optional[str]:
    """Invokes Gemini LLM for creative tailored date ideas."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if not api_key:
        return None

    models_to_try = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 600,
            "topP": 0.95
        }
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return text.strip()
        except Exception as e:
            print(f"[DATE_PLANNER] Gemini {model_name} error: {e}")
            continue

    return None


# ==============================================================================
# 3. CORE PUBLIC SERVICES
# ==============================================================================

async def generate_date_ideas(
    user1_profile: Dict[str, Any],
    user2_profile: Dict[str, Any],
    budget: str = "500",
    activity: str = "coffee",
    time_slot: Optional[str] = "Saturday, 5:30 PM",
    city_or_area: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Generates 3 customized date itineraries based on budget, activity, and both profiles.
    """
    clean_activity = activity.lower() if activity.lower() in DATE_TEMPLATES else "coffee"
    clean_budget = str(budget).replace("₹", "").strip()
    if clean_budget not in ["300", "500", "1000"]:
        clean_budget = "500"

    u1_name = user1_profile.get("name", "You")
    u2_name = user2_profile.get("name", "Match")
    location = city_or_area or user2_profile.get("locationName") or user1_profile.get("locationName") or "Nearby"

    # 1. Try Gemini LLM for hyper-personalized date ideas if API key present
    api_key = os.getenv("GEMINI_API_KEY", "").strip() or GEMINI_API_KEY
    if api_key:
        prompt = (
            f"You are Spark Date Planner, an expert real-world date concierge for modern couples.\n"
            f"Generate 3 creative, high-chemistry, realistic date itineraries for:\n"
            f"- User 1: {u1_name}, Interests: {user1_profile.get('interests', [])}\n"
            f"- User 2: {u2_name}, Interests: {user2_profile.get('interests', [])}\n"
            f"- City/Area: {location}\n"
            f"- Total Budget for Both: ₹{clean_budget}\n"
            f"- Primary Activity: {clean_activity.upper()}\n"
            f"- Desired Timing: {time_slot}\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. Realistic in Indian cities (Delhi NCR, Mumbai, Bangalore, Pune, etc.) within the specified budget (₹{clean_budget}).\n"
            f"2. High chemistry & zero awkwardness: combine primary activity with an easy transition (e.g. cafe + 20-min walk, or dessert).\n"
            f"3. Adult, mature, and comfortable for both men and women.\n"
            f"4. Return STRICTLY a valid JSON array of 3 objects with keys:\n"
            f"   'title': short catchy title with emoji,\n"
            f"   'vibe': 2-3 word vibe (e.g. 'Chill & Conversational'),\n"
            f"   'estimatedBudget': '₹{clean_budget}',\n"
            f"   'duration': e.g. '1.5 Hours',\n"
            f"   'description': 2-3 sentence engaging plan,\n"
            f"   'highlights': array of 3 quick bullet points.\n"
            f"Output strictly valid JSON, no backticks, no intro text."
        )
        llm_resp = await call_gemini_date_planner(prompt)
        if llm_resp:
            try:
                clean_json = llm_resp
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0]
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0]
                parsed = json.loads(clean_json.strip())
                if isinstance(parsed, list) and len(parsed) >= 2:
                    results = []
                    for idx, item in enumerate(parsed[:3]):
                        results.append({
                            "id": f"date-plan-{uuid.uuid4().hex[:8]}",
                            "title": item.get("title", f"{clean_activity.capitalize()} Date"),
                            "activity": clean_activity,
                            "estimatedBudget": f"₹{clean_budget}",
                            "vibe": item.get("vibe", "Chill & Relaxed"),
                            "duration": item.get("duration", "1.5 Hours"),
                            "description": item.get("description", ""),
                            "highlights": item.get("highlights", []),
                            "suggestedTime": time_slot,
                            "location": location,
                            "engine": "gemini-ai"
                        })
                    return results
            except Exception as e:
                print(f"[DATE_PLANNER] Parsing LLM response failed: {e}")

    # 2. Local Smart Fallback Engine
    pool = DATE_TEMPLATES.get(clean_activity, {}).get(clean_budget, [])
    if not pool:
        pool = DATE_TEMPLATES.get("coffee", {}).get("500", [])

    results = []
    for item in pool:
        results.append({
            "id": f"date-plan-{uuid.uuid4().hex[:8]}",
            "title": item["title"],
            "activity": clean_activity,
            "estimatedBudget": item["estimatedBudget"],
            "vibe": item["vibe"],
            "duration": item["duration"],
            "description": item["description"],
            "highlights": item["highlights"],
            "suggestedTime": time_slot,
            "location": location,
            "engine": "smart-context"
        })

    # If we have less than 3, add related activity
    if len(results) < 3:
        backup_pool = DATE_TEMPLATES.get("walk" if clean_activity != "walk" else "coffee", {}).get(clean_budget, [])
        for item in backup_pool:
            if len(results) >= 3:
                break
            results.append({
                "id": f"date-plan-{uuid.uuid4().hex[:8]}",
                "title": item["title"],
                "activity": clean_activity,
                "estimatedBudget": item["estimatedBudget"],
                "vibe": item["vibe"],
                "duration": item["duration"],
                "description": item["description"],
                "highlights": item["highlights"],
                "suggestedTime": time_slot,
                "location": location,
                "engine": "smart-context"
            })

    return results


def build_google_calendar_url(
    title: str,
    description: str,
    location: str,
    start_iso: Optional[str] = None
) -> str:
    """
    Builds a universal Google Calendar web intent URL that works on all Android and iOS
    devices without requiring any native calendar packages.
    """
    import urllib.parse
    base = "https://calendar.google.com/calendar/render?action=TEMPLATE"
    params = {
        "text": f"Date with {title} ✨",
        "details": f"{description}\n\nPlanned on Spark Dating App",
        "location": location or "Agreed Venue",
    }
    encoded = urllib.parse.urlencode(params)
    return f"{base}&{encoded}"
