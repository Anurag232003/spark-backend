# backend/services/circles_service.py
"""
Spark Circles — Dating + Social Discovery Service.
Allows users to discover & join passion communities (Cricket, Gaming, Harry Potter, College, etc.),
post discussions, participate in threads, and seamlessly bridge from shared interests into 1-on-1 dating matches.
"""

from datetime import datetime
from bson import ObjectId
from typing import Optional, List, Dict, Any

from database import (
    circles_collection,
    circle_members_collection,
    circle_posts_collection,
    circle_post_likes_collection,
    circle_comments_collection,
    users_collection,
    interactions_collection,
    matches_collection,
    messages_collection,
)
from services.text_moderator import is_message_clean

DEFAULT_CIRCLES = [
    {
        "slug": "cricket-lovers",
        "name": "Cricket Lovers",
        "category": "Sports",
        "icon": "🏏",
        "tagline": "Bleed Blue, IPL Banter & Turf Matches",
        "bannerGradient": ["#0f2027", "#203a43", "#2c5364"],
        "description": "Ind vs Pak match screening plans, IPL rivalry discussions, box turf cricket matches on weekends, and pure cricket obsession!",
        "tags": ["Cricket", "IPL", "Team India", "Turf Cricket"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "gaming-squad",
        "name": "Gaming Squad",
        "category": "Gaming",
        "icon": "🎮",
        "tagline": "BGMI, Valorant & Chill Co-op",
        "bannerGradient": ["#1f1c2c", "#928dab", "#2c3e50"],
        "description": "Find duo partners for Valorant rank push, late-night BGMI squad matches, PS5 enthusiasts, and chill Discord hangout gaming sessions.",
        "tags": ["Valorant", "BGMI", "Steam", "PlayStation", "Discord"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "harry-potter",
        "name": "Harry Potter Fans",
        "category": "Fandom",
        "icon": "⚡",
        "tagline": "Potterheads & Hogwarts Debates",
        "bannerGradient": ["#3a1c71", "#d76d77", "#ffaf7b"],
        "description": "Gryffindor vs Slytherin debates, Potter trivia, butterbeer cafe meetups, and finding someone who understands your magical references.",
        "tags": ["Potterhead", "Hogwarts", "Gryffindor", "Slytherin"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "college-campus",
        "name": "College & Campus",
        "category": "Campus",
        "icon": "🎓",
        "tagline": "Campus Life, Fests & Hangouts",
        "bannerGradient": ["#11998e", "#38ef7d", "#0575e6"],
        "description": "College fests, exam study dates, campus gossip, canteen chai breaks, and connecting with students from your city.",
        "tags": ["College Life", "Fests", "Canteen Chai", "Campus Dating"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "coffee-lovers",
        "name": "Coffee Lovers",
        "category": "Lifestyle",
        "icon": "☕",
        "tagline": "Aesthetic Cafes & Pour Overs",
        "bannerGradient": ["#3e2723", "#4e342e", "#8d6e63"],
        "description": "Third-wave cafes, specialty espresso roasters, aesthetic work-from-cafe afternoons, and finding the perfect first coffee date partner.",
        "tags": ["Espresso", "Specialty Coffee", "Cafe Hopper", "Cold Brew"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "gym-fitness",
        "name": "Gym & Fitness",
        "category": "Fitness",
        "icon": "🏋️",
        "tagline": "Workout Splits & Gym Buddies",
        "bannerGradient": ["#141e30", "#243b55", "#e52d27"],
        "description": "Push/Pull/Legs splits, workout motivation, morning running clubs, healthy protein recipe swaps, and fitness accountability buddies.",
        "tags": ["Gym Bro", "Calisthenics", "Running", "Fitness Date"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "music-concerts",
        "name": "Music & Concerts",
        "category": "Music",
        "icon": "🎵",
        "tagline": "Indie Gigs, Sunburn & Spotify Blends",
        "bannerGradient": ["#8e2de2", "#4a00e0", "#f107a3"],
        "description": "Indie concerts, EDM festivals, sharing Spotify blends, acoustic guitar jams, and finding someone who shares your music taste.",
        "tags": ["Indie Music", "Concerts", "Spotify Blend", "Sunburn"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "cinephiles-cinema",
        "name": "Cinephiles & Cinema",
        "category": "Entertainment",
        "icon": "🎬",
        "tagline": "Bollywood, Sci-Fi & Anime Reviews",
        "bannerGradient": ["#232526", "#414345", "#e65c00"],
        "description": "Nolan mindbenders, late-night Anime binges, classic Bollywood romance, film festivals, and finding your IMAX seatmate.",
        "tags": ["Cinema", "Anime", "Bollywood", "Movie Date"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "tech-builders",
        "name": "Tech & Builders",
        "category": "Tech",
        "icon": "💻",
        "tagline": "Startups, AI, Code & Designers",
        "bannerGradient": ["#0f0c29", "#302b63", "#24243e"],
        "description": "Tech founders, developers, AI tinkerers, UI/UX designers, and ambitious creators building the future over weekend hackathons.",
        "tags": ["Startups", "AI", "Coding", "Tech Networking"],
        "member_count": 0,
        "post_count": 0,
    },
    {
        "slug": "travel-roadtrips",
        "name": "Travel & Roadtrips",
        "category": "Travel",
        "icon": "🏔️",
        "tagline": "Weekend Treks, Mountains & Wanderlust",
        "bannerGradient": ["#134e5e", "#71b280", "#2c7744"],
        "description": "Himalayan treks, weekend road trips, monsoon drives, beach camping, and discovering hidden travel gems across India.",
        "tags": ["Roadtrips", "Trekking", "Mountains", "Wanderlust"],
        "member_count": 0,
        "post_count": 0,
    },
]

def ensure_seeded_circles():
    """
    Ensures all default circles exist in the database on startup.
    Idempotent: updates missing circles and syncs strictly real member and post counts.
    """
    try:
        for c in DEFAULT_CIRCLES:
            existing = circles_collection.find_one({"slug": c["slug"]})
            if not existing:
                doc = {
                    **c,
                    "member_count": 0,
                    "post_count": 0,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
                circles_collection.insert_one(doc)
            else:
                # Keep metadata fresh
                circles_collection.update_one(
                    {"slug": c["slug"]},
                    {"$set": {
                        "name": c["name"],
                        "category": c["category"],
                        "icon": c["icon"],
                        "tagline": c["tagline"],
                        "bannerGradient": c["bannerGradient"],
                        "description": c["description"],
                        "tags": c["tags"],
                    }}
                )

        # Sync strictly accurate real counts across all circles
        for c in circles_collection.find({}):
            c_id = str(c["_id"])
            real_members = circle_members_collection.count_documents({"circle_id": c_id})
            real_posts = circle_posts_collection.count_documents({"circle_id": c_id})
            circles_collection.update_one(
                {"_id": c["_id"]},
                {"$set": {
                    "member_count": real_members,
                    "post_count": real_posts,
                }}
            )
    except Exception as e:
        print(f"[CIRCLES] ensure_seeded_circles error: {e}")

def get_circles_list(user_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns list of circles with membership status and strictly real counts for the user.
    """
    query: Dict[str, Any] = {}
    if category and category.lower() != "all":
        query["category"] = {"$regex": f"^{category}$", "$options": "i"}

    circles = list(circles_collection.find(query).sort("member_count", -1))
    
    # Get user's joined circles
    joined_circle_ids = set()
    if user_id:
        user_memberships = circle_members_collection.find({"user_id": user_id})
        for m in user_memberships:
            joined_circle_ids.add(str(m.get("circle_id")))

    result = []
    for c in circles:
        c_id = str(c["_id"])
        is_joined = c_id in joined_circle_ids
        
        # Real-time member and post count strictly from actual database collections
        actual_members = circle_members_collection.count_documents({"circle_id": c_id})
        actual_posts = circle_posts_collection.count_documents({"circle_id": c_id})

        result.append({
            "id": c_id,
            "slug": c.get("slug", ""),
            "name": c.get("name", "Spark Circle"),
            "category": c.get("category", "General"),
            "icon": c.get("icon", "✨"),
            "tagline": c.get("tagline", ""),
            "bannerGradient": c.get("bannerGradient", ["#784cfb", "#ff3366"]),
            "description": c.get("description", ""),
            "tags": c.get("tags", []),
            "memberCount": actual_members,
            "postCount": actual_posts,
            "isJoined": is_joined,
        })

    # Sort joined circles first, then member count, then name
    result.sort(key=lambda x: (not x["isJoined"], -x["memberCount"], x["name"]))
    return result

def get_circle_detail(circle_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches detailed view of a specific circle with strictly real counts.
    """
    try:
        obj_id = ObjectId(circle_id)
        query = {"_id": obj_id}
    except Exception:
        query = {"_id": circle_id}

    c = circles_collection.find_one(query)
    if not c:
        return None

    c_id = str(c["_id"])
    is_joined = bool(circle_members_collection.find_one({"circle_id": c_id, "user_id": user_id}))
    actual_members = circle_members_collection.count_documents({"circle_id": c_id})
    actual_posts = circle_posts_collection.count_documents({"circle_id": c_id})

    return {
        "id": c_id,
        "slug": c.get("slug", ""),
        "name": c.get("name", "Spark Circle"),
        "category": c.get("category", "General"),
        "icon": c.get("icon", "✨"),
        "tagline": c.get("tagline", ""),
        "bannerGradient": c.get("bannerGradient", ["#784cfb", "#ff3366"]),
        "description": c.get("description", ""),
        "tags": c.get("tags", []),
        "memberCount": actual_members,
        "postCount": actual_posts,
        "isJoined": is_joined,
    }

def join_circle(circle_id: str, user_id: str) -> Dict[str, Any]:
    """
    Adds user to the circle membership.
    """
    circle = get_circle_detail(circle_id, user_id)
    if not circle:
        raise ValueError("Circle not found")

    circle_members_collection.update_one(
        {"circle_id": circle_id, "user_id": user_id},
        {"$setOnInsert": {"circle_id": circle_id, "user_id": user_id, "joined_at": datetime.utcnow()}},
        upsert=True
    )
    # Sync exact real count
    actual_count = circle_members_collection.count_documents({"circle_id": circle_id})
    circles_collection.update_one(
        {"_id": ObjectId(circle_id) if ObjectId.is_valid(circle_id) else circle_id},
        {"$set": {"member_count": actual_count}}
    )
    return {"status": "SUCCESS", "isJoined": True, "circleId": circle_id, "memberCount": actual_count}

def leave_circle(circle_id: str, user_id: str) -> Dict[str, Any]:
    """
    Removes user from the circle membership.
    """
    circle_members_collection.delete_one({"circle_id": circle_id, "user_id": user_id})
    actual_count = circle_members_collection.count_documents({"circle_id": circle_id})
    circles_collection.update_one(
        {"_id": ObjectId(circle_id) if ObjectId.is_valid(circle_id) else circle_id},
        {"$set": {"member_count": actual_count}}
    )
    return {"status": "SUCCESS", "isJoined": False, "circleId": circle_id, "memberCount": actual_count}

def get_circle_posts(circle_id: str, user_id: str, limit: int = 30, skip: int = 0) -> List[Dict[str, Any]]:
    """
    Fetches the discussion feed for a circle with like status and author info.
    """
    posts = list(
        circle_posts_collection.find({"circle_id": circle_id})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    # Preload user likes for this batch
    post_ids = [str(p["_id"]) for p in posts]
    liked_post_ids = set()
    if user_id and post_ids:
        likes = circle_post_likes_collection.find({
            "post_id": {"$in": post_ids},
            "user_id": user_id
        })
        for l in likes:
            liked_post_ids.add(str(l.get("post_id")))

    # Collect author ids to fetch fresh profile pictures / names
    author_ids = list({p.get("author_id") for p in posts if p.get("author_id")})
    user_map = {}
    if author_ids:
        u_docs = users_collection.find({"id": {"$in": author_ids}})
        for u in u_docs:
            user_map[u.get("id")] = u

    results = []
    for p in posts:
        p_id = str(p["_id"])
        a_id = p.get("author_id", "")
        u_profile = user_map.get(a_id, {})

        # Compute display author info
        author_name = u_profile.get("name") or p.get("author_name", "Spark Member")
        photos = u_profile.get("photos", [])
        author_photo = photos[0] if photos else p.get("author_photo", "")
        author_age = u_profile.get("age") or p.get("author_age", 22)
        author_bio = u_profile.get("bio") or ""
        author_verified = u_profile.get("is_photo_verified") or u_profile.get("isPhotoVerified") or False
        author_interests = u_profile.get("interests") or []

        created_at_dt = p.get("created_at")
        created_at_iso = created_at_dt.isoformat() if isinstance(created_at_dt, datetime) else str(created_at_dt)

        results.append({
            "id": p_id,
            "circleId": circle_id,
            "authorId": a_id,
            "authorName": author_name,
            "authorPhoto": author_photo,
            "authorAge": author_age,
            "authorBio": author_bio,
            "authorVerified": author_verified,
            "authorInterests": author_interests,
            "content": p.get("content", ""),
            "mediaUrl": p.get("media_url"),
            "likesCount": p.get("likes_count", 0),
            "commentsCount": p.get("comments_count", 0),
            "isLiked": p_id in liked_post_ids,
            "createdAt": created_at_iso,
        })

    return results

def create_circle_post(
    circle_id: str,
    user_id: str,
    content: str,
    media_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new post in a circle after passing content moderation.
    """
    trimmed = content.strip()
    if not trimmed:
        raise ValueError("Post content cannot be empty")
    if len(trimmed) > 1000:
        raise ValueError("Post content exceeds 1000 characters")

    # Content safety check
    if not is_message_clean(trimmed):
        raise ValueError("Post contains inappropriate language or prohibited content")

    # Author profile
    user = users_collection.find_one({"id": user_id})
    if not user:
        raise ValueError("User profile not found")

    photos = user.get("photos", [])
    author_photo = photos[0] if photos else ""
    author_name = user.get("name", "Spark Member")
    author_age = user.get("age", 22)
    author_verified = user.get("is_photo_verified") or user.get("isPhotoVerified") or False

    post_doc = {
        "circle_id": circle_id,
        "author_id": user_id,
        "author_name": author_name,
        "author_photo": author_photo,
        "author_age": author_age,
        "author_verified": author_verified,
        "content": trimmed,
        "media_url": media_url,
        "likes_count": 0,
        "comments_count": 0,
        "created_at": datetime.utcnow(),
    }

    inserted = circle_posts_collection.insert_one(post_doc)
    post_id = str(inserted.inserted_id)

    # Auto join user to circle if they posted in it
    circle_members_collection.update_one(
        {"circle_id": circle_id, "user_id": user_id},
        {"$setOnInsert": {"circle_id": circle_id, "user_id": user_id, "joined_at": datetime.utcnow()}},
        upsert=True
    )

    # Sync real counts in circle
    actual_posts = circle_posts_collection.count_documents({"circle_id": circle_id})
    actual_members = circle_members_collection.count_documents({"circle_id": circle_id})
    circles_collection.update_one(
        {"_id": ObjectId(circle_id) if ObjectId.is_valid(circle_id) else circle_id},
        {"$set": {"post_count": actual_posts, "member_count": actual_members}}
    )

    return {
        "id": post_id,
        "circleId": circle_id,
        "authorId": user_id,
        "authorName": author_name,
        "authorPhoto": author_photo,
        "authorAge": author_age,
        "authorBio": user.get("bio", ""),
        "authorVerified": author_verified,
        "authorInterests": user.get("interests", []),
        "content": trimmed,
        "mediaUrl": media_url,
        "likesCount": 0,
        "commentsCount": 0,
        "isLiked": False,
        "createdAt": post_doc["created_at"].isoformat(),
    }

def toggle_post_like(post_id: str, user_id: str) -> Dict[str, Any]:
    """
    Toggles a like on a circle post.
    """
    existing = circle_post_likes_collection.find_one({"post_id": post_id, "user_id": user_id})
    
    post_query = {"_id": ObjectId(post_id) if ObjectId.is_valid(post_id) else post_id}

    if existing:
        # Unlike
        circle_post_likes_collection.delete_one({"_id": existing["_id"]})
        updated = circle_posts_collection.find_one_and_update(
            post_query,
            {"$inc": {"likes_count": -1}},
            return_document=True
        )
        new_count = max(0, updated.get("likes_count", 0)) if updated else 0
        return {"status": "SUCCESS", "isLiked": False, "likesCount": new_count, "postId": post_id}
    else:
        # Like
        circle_post_likes_collection.insert_one({
            "post_id": post_id,
            "user_id": user_id,
            "created_at": datetime.utcnow()
        })
        updated = circle_posts_collection.find_one_and_update(
            post_query,
            {"$inc": {"likes_count": 1}},
            return_document=True
        )
        new_count = updated.get("likes_count", 1) if updated else 1
        return {"status": "SUCCESS", "isLiked": True, "likesCount": new_count, "postId": post_id}

def get_post_comments(post_id: str) -> List[Dict[str, Any]]:
    """
    Fetches comments for a specific circle post.
    """
    comments = list(
        circle_comments_collection.find({"post_id": post_id})
        .sort("created_at", 1)
        .limit(100)
    )

    # Collect author ids for latest profile info
    author_ids = list({c.get("author_id") for c in comments if c.get("author_id")})
    user_map = {}
    if author_ids:
        u_docs = users_collection.find({"id": {"$in": author_ids}})
        for u in u_docs:
            user_map[u.get("id")] = u

    results = []
    for c in comments:
        c_id = str(c["_id"])
        a_id = c.get("author_id", "")
        u_profile = user_map.get(a_id, {})
        photos = u_profile.get("photos", [])

        created_dt = c.get("created_at")
        created_iso = created_dt.isoformat() if isinstance(created_dt, datetime) else str(created_dt)

        results.append({
            "id": c_id,
            "postId": post_id,
            "authorId": a_id,
            "authorName": u_profile.get("name") or c.get("author_name", "Spark Member"),
            "authorPhoto": photos[0] if photos else c.get("author_photo", ""),
            "authorAge": u_profile.get("age") or c.get("author_age", 22),
            "authorVerified": u_profile.get("is_photo_verified") or u_profile.get("isPhotoVerified") or False,
            "content": c.get("content", ""),
            "createdAt": created_iso,
        })
    return results

def create_post_comment(post_id: str, user_id: str, content: str) -> Dict[str, Any]:
    """
    Adds a comment to a circle post.
    """
    trimmed = content.strip()
    if not trimmed:
        raise ValueError("Comment cannot be empty")
    if len(trimmed) > 500:
        raise ValueError("Comment exceeds 500 characters")

    if not is_message_clean(trimmed):
        raise ValueError("Comment contains inappropriate language")

    user = users_collection.find_one({"id": user_id})
    if not user:
        raise ValueError("User profile not found")

    photos = user.get("photos", [])
    author_photo = photos[0] if photos else ""
    author_name = user.get("name", "Spark Member")
    author_age = user.get("age", 22)
    author_verified = user.get("is_photo_verified") or user.get("isPhotoVerified") or False

    comment_doc = {
        "post_id": post_id,
        "author_id": user_id,
        "author_name": author_name,
        "author_photo": author_photo,
        "author_age": author_age,
        "author_verified": author_verified,
        "content": trimmed,
        "created_at": datetime.utcnow(),
    }

    inserted = circle_comments_collection.insert_one(comment_doc)

    # Increment comment counter on the post
    circle_posts_collection.update_one(
        {"_id": ObjectId(post_id) if ObjectId.is_valid(post_id) else post_id},
        {"$inc": {"comments_count": 1}}
    )

    return {
        "id": str(inserted.inserted_id),
        "postId": post_id,
        "authorId": user_id,
        "authorName": author_name,
        "authorPhoto": author_photo,
        "authorAge": author_age,
        "authorVerified": author_verified,
        "content": trimmed,
        "createdAt": comment_doc["created_at"].isoformat(),
    }

def connect_from_circle(
    current_user_id: str,
    target_user_id: str,
    circle_id: str,
    post_id: Optional[str] = None,
    opening_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Flagship Dating Bridge:
    Allows a user who discovers someone in a Circle to send an instant 'Spark Connection' (Like + Context Message).
    If reciprocal like exists, immediately creates a match with the Circle context.
    """
    if current_user_id == target_user_id:
        raise ValueError("Cannot connect with yourself")

    target_user = users_collection.find_one({"id": target_user_id})
    if not target_user:
        raise ValueError("Target user profile not found")

    circle = get_circle_detail(circle_id, current_user_id)
    circle_name = circle.get("name", "Spark Circle") if circle else "Spark Circle"

    # 1. Record interaction
    interaction_doc = {
        "from_user_id": current_user_id,
        "target_user_id": target_user_id,
        "type": "LIKE",
        "source": "SPARK_CIRCLE",
        "circle_id": circle_id,
        "circle_name": circle_name,
        "post_id": post_id,
        "opening_message": opening_message,
        "created_at": datetime.utcnow(),
    }

    interactions_collection.update_one(
        {"from_user_id": current_user_id, "target_user_id": target_user_id},
        {"$set": interaction_doc},
        upsert=True
    )

    # 2. Check for reciprocal like
    reciprocal = interactions_collection.find_one({
        "from_user_id": target_user_id,
        "target_user_id": current_user_id,
        "type": "LIKE",
    })

    if reciprocal:
        # It's a match!
        pair_key = f"{min(current_user_id, target_user_id)}_{max(current_user_id, target_user_id)}"
        existing_match = matches_collection.find_one({"pair_key": pair_key})

        if not existing_match:
            match_doc = {
                "pair_key": pair_key,
                "user1_id": min(current_user_id, target_user_id),
                "user2_id": max(current_user_id, target_user_id),
                "status": "ACTIVE",
                "matched_via": "SPARK_CIRCLE",
                "circle_name": circle_name,
                "first_move_made": True,
                "created_at": datetime.utcnow(),
            }
            inserted_match = matches_collection.insert_one(match_doc)
            match_id = str(inserted_match.inserted_id)

            # Insert initial circle icebreaker greeting into chat
            greeting = f"⚡ Connected via {circle_name}! \"{opening_message}\"" if opening_message else f"⚡ Connected via {circle_name}!"
            first_msg = {
                "match_id": match_id,
                "sender_id": current_user_id,
                "receiver_id": target_user_id,
                "text": greeting,
                "is_screenshot": False,
                "is_date_proposal": False,
                "timestamp": datetime.utcnow(),
            }
            messages_collection.insert_one(first_msg)

            return {
                "status": "MATCHED",
                "isMatch": True,
                "matchId": match_id,
                "circleName": circle_name,
                "targetUser": {
                    "id": target_user.get("id"),
                    "name": target_user.get("name"),
                    "photos": target_user.get("photos", []),
                },
                "message": f"It's a Spark Match! You and {target_user.get('name')} connected via {circle_name}!"
            }

    return {
        "status": "LIKED",
        "isMatch": False,
        "circleName": circle_name,
        "targetUser": {
            "id": target_user.get("id"),
            "name": target_user.get("name"),
            "photos": target_user.get("photos", []),
        },
        "message": f"Spark Connection sent to {target_user.get('name')} via {circle_name}!"
    }
