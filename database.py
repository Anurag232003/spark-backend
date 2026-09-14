# backend/database.py
import os
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables from .env
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is not set. Please define it in your .env file or environment.")

# Configure robust DNS resolver for MongoDB Atlas SRV connection on Windows
try:
    import dns.resolver
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ["8.8.8.8", "1.1.1.1", "8.8.4.4"]
    dns.resolver.default_resolver = resolver
except Exception as _e:
    pass

client = MongoClient(MONGO_URI)
db = client["dating_app_db"]

users_collection = db["users"]
otp_collection = db["otp_store"]
interactions_collection = db["interactions"]
matches_collection = db["matches"]
messages_collection = db["messages"]
# backend/database.py (collections)
blocks_collection = db["blocks"]
reports_collection = db["reports"]
uploads_collection = db["user_uploads"]
refresh_tokens_collection = db["refresh_tokens"]
moderation_actions_collection = db["moderation_actions"]
circles_collection = db["circles"]
circle_members_collection = db["circle_members"]
circle_posts_collection = db["circle_posts"]
circle_post_likes_collection = db["circle_post_likes"]
circle_comments_collection = db["circle_comments"]
duos_collection = db["duos"]
duo_interactions_collection = db["duo_interactions"]
chemistry_profiles_collection = db["chemistry_profiles"]
chemistry_sessions_collection = db["chemistry_sessions"]
trusted_contacts_collection = db["trusted_contacts"]
date_checkins_collection = db["date_checkins"]
notifications_collection = db["notifications"]
daily_sparks_collection = db["daily_sparks"]
spark_challenges_collection = db["spark_challenges"]
secret_interests_collection = db["secret_interests"]
secret_matches_collection = db["secret_matches"]

def init_db_indexes():
    """
    Initializes explicit performance and uniqueness indexes across all MongoDB collections.
    Ensures O(1) / O(log N) lookup speeds as the dataset scales.
    """
    try:
        # 1. users collection
        # users.phone: Unique index for authentication lookup and preventing duplicate accounts
        users_collection.create_index([("phone", 1)], unique=True, sparse=True)
        # users.id: Unique index for primary user lookups (auth session, profile fetch, updates)
        users_collection.create_index([("id", 1)], unique=True, sparse=True)
        # Geospatial 2dsphere index on location for radius queries and distance ranking
        users_collection.create_index([("location", "2dsphere")], sparse=True)

        # 2. interactions collection
        # interactions.from_user_id: Fast lookup of candidate profiles swiped by the user
        interactions_collection.create_index([("from_user_id", 1)])
        # interactions.target_user_id: Fast lookup of incoming likes on user's profile
        interactions_collection.create_index([("target_user_id", 1)])
        # Compound index for incoming likes priority boost (target_user_id + type)
        interactions_collection.create_index([("target_user_id", 1), ("type", 1)])
        # Unique compound index to guarantee at most one swipe interaction per pair
        interactions_collection.create_index(
            [("from_user_id", 1), ("target_user_id", 1)],
            unique=True
        )

        # 3. matches collection
        # matches.user1_id: Fast match queries for participant 1
        matches_collection.create_index([("user1_id", 1)])
        # matches.user2_id: Fast match queries for participant 2
        matches_collection.create_index([("user2_id", 1)])
        # Compound status indexes for active match queries
        matches_collection.create_index([("user1_id", 1), ("status", 1)])
        matches_collection.create_index([("user2_id", 1), ("status", 1)])
        # Unique partial index on active matches per pair_key to strictly prevent duplicate matches
        matches_collection.create_index([("pair_key", 1)], unique=True, sparse=True)
        # Compound index for 24-hour match expiry background worker
        matches_collection.create_index([("status", 1), ("first_move_made", 1), ("first_move_deadline", 1)])

        # 4. messages collection
        # messages.match_id: Fast lookup of all messages in a match/chat
        messages_collection.create_index([("match_id", 1)])
        # Compound index for ordered conversation retrieval by timestamp
        messages_collection.create_index([("match_id", 1), ("timestamp", 1)])

        # 5. blocks collection
        # blocks.blocker_user_id: Fast lookup of users blocked by current user
        blocks_collection.create_index([("blocker_user_id", 1)])
        # blocks.target_user_id: Fast lookup of users who have blocked current user
        blocks_collection.create_index([("target_user_id", 1)])
        # Unique compound index to prevent duplicate block records
        blocks_collection.create_index(
            [("blocker_user_id", 1), ("target_user_id", 1)],
            unique=True
        )

        # 6. otp_store collection
        otp_collection.create_index([("phone", 1)])
        otp_collection.create_index([("expires_at", 1)], expireAfterSeconds=0)

        # 7. refresh_tokens collection
        refresh_tokens_collection.create_index([("jti", 1)], unique=True, sparse=True)
        refresh_tokens_collection.create_index([("user_id", 1)])

        # 8. reports collection
        # Index for moderation queue sorted by status and submission date
        reports_collection.create_index([("status", 1), ("created_at", -1)])
        reports_collection.create_index([("reported_user_id", 1)])
        # Unique index: one report per (reporter, target) pair
        reports_collection.create_index(
            [("reporter_user_id", 1), ("reported_user_id", 1)],
            unique=True
        )

        # 9. moderation_actions collection
        moderation_actions_collection.create_index([("report_id", 1)])
        moderation_actions_collection.create_index([("target_user_id", 1)])

        # 10. Spark Circles collections
        circles_collection.create_index([("slug", 1)], unique=True, sparse=True)
        circles_collection.create_index([("category", 1)])
        circle_members_collection.create_index([("circle_id", 1), ("user_id", 1)], unique=True)
        circle_members_collection.create_index([("user_id", 1)])
        circle_posts_collection.create_index([("circle_id", 1), ("created_at", -1)])
        circle_posts_collection.create_index([("author_id", 1)])
        circle_post_likes_collection.create_index([("post_id", 1), ("user_id", 1)], unique=True)
        circle_comments_collection.create_index([("post_id", 1), ("created_at", 1)])

        # 11. Double Date Duos collections
        duos_collection.create_index([("invite_code", 1)], unique=True, sparse=True)
        duos_collection.create_index([("user1_id", 1)])
        duos_collection.create_index([("user2_id", 1)])
        duos_collection.create_index([("status", 1)])
        duo_interactions_collection.create_index([("from_duo_id", 1), ("target_duo_id", 1)], unique=True)
        duo_interactions_collection.create_index([("target_duo_id", 1)])

        # 12. Spark Chemistry Game collections
        chemistry_profiles_collection.create_index([("user_id", 1)], unique=True)
        chemistry_sessions_collection.create_index([("session_id", 1)], unique=True, sparse=True)
        chemistry_sessions_collection.create_index([("match_id", 1)])
        chemistry_sessions_collection.create_index([("created_at", -1)])

        # 13. Date Safety Center collections
        trusted_contacts_collection.create_index([("user_id", 1)], unique=True)
        date_checkins_collection.create_index([("checkin_id", 1)], unique=True, sparse=True)
        date_checkins_collection.create_index([("user_id", 1), ("status", 1)])
        date_checkins_collection.create_index([("created_at", -1)])

        # 14. Notifications collection
        notifications_collection.create_index([("user_id", 1), ("read", 1)])
        notifications_collection.create_index([("created_at", -1)])

        # 15. 24-Hour Spark & Conversation Challenge collections
        daily_sparks_collection.create_index([("user_id", 1), ("drop_date", 1)], unique=True)
        daily_sparks_collection.create_index([("expires_at", 1)])
        spark_challenges_collection.create_index([("match_id", 1)], unique=True)
        spark_challenges_collection.create_index([("expires_at", 1), ("is_completed", 1)])

        # 16. Secret Interest Match collections
        secret_interests_collection.create_index([("user_id", 1)], unique=True)
        secret_matches_collection.create_index([("pair_key", 1)], unique=True)
        secret_matches_collection.create_index([("user1_id", 1), ("is_revealed", 1)])
        secret_matches_collection.create_index([("user2_id", 1), ("is_revealed", 1)])
        secret_matches_collection.create_index([("cycle_expires_at", 1)])
    except Exception as e:
        print(f"Warning: Index creation deferred or failed: {e}")

init_db_indexes()

print("Connected to MongoDB successfully!")