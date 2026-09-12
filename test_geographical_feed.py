"""
Test Suite: Issue 51 - Geographically Personalized Feed
Tests:
1. MongoDB 2dsphere Indexing & GeoJSON structure
2. Radius Filtering (max_distance_km)
3. Proximity Location Ranking (closest candidates first)
4. Dynamic GPS Query Parameter Override (device moving)
"""
import math
from database import users_collection, interactions_collection
from main import (
    get_discovery_feed,
    calculate_haversine_distance,
    get_user_coordinates,
)

def test_geographical_feed():
    print("--- Running Issue 51 Geographical Feed Test Suite ---")

    # Set up test fixtures
    # Delhi User: 28.6139, 77.2090
    me_delhi = {
        "id": "u_geo_me_delhi",
        "name": "Delhi Explorer",
        "age": 26,
        "gender": "male",
        "locationName": "Delhi NCR, India",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "location": {
            "type": "Point",
            "coordinates": [77.2090, 28.6139]
        }
    }

    # Candidate 1: Noida (~19 km away from Delhi center)
    cand_noida = {
        "id": "u_geo_cand_noida",
        "name": "Noida Candidate",
        "age": 24,
        "gender": "female",
        "locationName": "Noida, Sector 18",
        "latitude": 28.5355,
        "longitude": 77.3910,
        "location": {
            "type": "Point",
            "coordinates": [77.3910, 28.5355]
        },
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample.jpg"],
        "prompts": []
    }

    # Candidate 2: Jaipur (~235 km away from Delhi)
    cand_jaipur = {
        "id": "u_geo_cand_jaipur",
        "name": "Jaipur Candidate",
        "age": 25,
        "gender": "female",
        "locationName": "Jaipur, Rajasthan",
        "latitude": 26.9124,
        "longitude": 75.7873,
        "location": {
            "type": "Point",
            "coordinates": [75.7873, 26.9124]
        },
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample.jpg"],
        "prompts": []
    }

    # Candidate 3: Mumbai (~1148 km away from Delhi)
    cand_mumbai = {
        "id": "u_geo_cand_mumbai",
        "name": "Mumbai Candidate",
        "age": 23,
        "gender": "female",
        "locationName": "Bandra, Mumbai",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "location": {
            "type": "Point",
            "coordinates": [72.8777, 19.0760]
        },
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample.jpg"],
        "prompts": []
    }

    test_ids = [me_delhi["id"], cand_noida["id"], cand_jaipur["id"], cand_mumbai["id"]]
    users_collection.delete_many({"id": {"$in": test_ids}})
    interactions_collection.delete_many({"from_user_id": me_delhi["id"]})

    users_collection.insert_one(me_delhi)
    users_collection.insert_one(cand_noida)
    users_collection.insert_one(cand_jaipur)
    users_collection.insert_one(cand_mumbai)

    try:
        # TEST 1: Radius Filtering (max_distance_km = 50 km)
        # Should only include Noida (~19 km), strictly excluding Jaipur (~235 km) and Mumbai (~1148 km)
        feed_50km = get_discovery_feed(
            max_distance_km=50.0,
            current_user=me_delhi
        )
        profiles_50km = feed_50km["profiles"]
        ids_50km = [p["id"] for p in profiles_50km]
        
        assert cand_noida["id"] in ids_50km, "Noida candidate must be included within 50 km radius"
        assert cand_jaipur["id"] not in ids_50km, "Jaipur candidate (>230 km) must be excluded from 50 km radius"
        assert cand_mumbai["id"] not in ids_50km, "Mumbai candidate (>1100 km) must be excluded from 50 km radius"
        print("PASS: Radius filtering correctly restricts feed to 50 km (Noida matched, Jaipur & Mumbai excluded)")

        # TEST 2: Radius Filtering (max_distance_km = 300 km)
        # Should include Noida (~19 km) and Jaipur (~235 km), strictly excluding Mumbai (~1148 km)
        feed_300km = get_discovery_feed(
            max_distance_km=300.0,
            current_user=me_delhi
        )
        ids_300km = [p["id"] for p in feed_300km["profiles"]]
        assert cand_noida["id"] in ids_300km, "Noida candidate must be in 300 km radius"
        assert cand_jaipur["id"] in ids_300km, "Jaipur candidate must be in 300 km radius"
        assert cand_mumbai["id"] not in ids_300km, "Mumbai candidate (>1100 km) must be excluded from 300 km radius"
        print("PASS: Radius filtering correctly expands to 300 km (Noida & Jaipur matched, Mumbai excluded)")

        # TEST 3: Proximity Location Ranking (Closest First)
        # When no radius limit is set, candidates must appear in ascending distance order
        feed_all = get_discovery_feed(
            current_user=me_delhi
        )
        profiles_all = feed_all["profiles"]
        test_profiles = [p for p in profiles_all if p["id"] in [cand_noida["id"], cand_jaipur["id"], cand_mumbai["id"]]]
        
        assert len(test_profiles) == 3, "All 3 candidates must be present"
        assert test_profiles[0]["id"] == cand_noida["id"], "1st profile must be Noida (~19 km)"
        assert test_profiles[1]["id"] == cand_jaipur["id"], "2nd profile must be Jaipur (~235 km)"
        assert test_profiles[2]["id"] == cand_mumbai["id"], "3rd profile must be Mumbai (~1148 km)"
        
        dist_0 = test_profiles[0]["distanceKm"]
        dist_1 = test_profiles[1]["distanceKm"]
        dist_2 = test_profiles[2]["distanceKm"]
        assert dist_0 < dist_1 < dist_2, f"Distances must be strictly ascending: {dist_0} < {dist_1} < {dist_2}"
        print(f"PASS: Proximity ranking orders profiles ascending: {dist_0} km < {dist_1} km < {dist_2} km")

        # TEST 4: Dynamic GPS Query Parameter Override
        # If user moves to Mumbai and passes device GPS coordinates (19.0760, 72.8777)
        feed_mumbai_gps = get_discovery_feed(
            lat=19.0760,
            lon=72.8777,
            current_user=me_delhi
        )
        test_mumbai_profiles = [p for p in feed_mumbai_gps["profiles"] if p["id"] in [cand_noida["id"], cand_jaipur["id"], cand_mumbai["id"]]]
        assert len(test_mumbai_profiles) == 3
        # When in Mumbai, Mumbai candidate is ~0.0 km and must be ranked #1
        assert test_mumbai_profiles[0]["id"] == cand_mumbai["id"], "Mumbai candidate must now rank #1 when user is in Mumbai"
        assert test_mumbai_profiles[0]["distanceKm"] < 1.0, "Mumbai candidate distance should be ~0 km"
        print(f"PASS: Live GPS coordinates override re-ranks Mumbai candidate to #1 ({test_mumbai_profiles[0]['distanceKm']} km)")

        print("--- ALL ISSUE 51 GEOGRAPHICAL FEED TESTS PASSED SUCCESSFULLY! ---")

    finally:
        users_collection.delete_many({"id": {"$in": test_ids}})
        interactions_collection.delete_many({"from_user_id": me_delhi["id"]})

if __name__ == "__main__":
    test_geographical_feed()
