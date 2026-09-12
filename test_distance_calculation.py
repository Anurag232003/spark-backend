"""
Test Suite: Real Haversine Distance Calculation & Location Endpoints
"""
import math
from database import users_collection, interactions_collection, blocks_collection
import main
from main import (
    calculate_haversine_distance,
    get_user_coordinates,
    get_discovery_feed,
    update_my_location,
    UpdateLocationRequest,
)

def test_distance_calculation():
    print("--- Running Distance Calculation & Feed Location Tests ---")

    # 1. Test Haversine formula directly
    # Delhi to Mumbai distance is ~1148 km
    delhi_lat, delhi_lon = 28.6139, 77.2090
    mumbai_lat, mumbai_lon = 19.0760, 72.8777
    dist_delhi_mumbai = calculate_haversine_distance(delhi_lat, delhi_lon, mumbai_lat, mumbai_lon)
    print(f"Calculated Delhi-Mumbai distance: {dist_delhi_mumbai} km")
    assert 1140 <= dist_delhi_mumbai <= 1160, f"Expected ~1148 km, got {dist_delhi_mumbai}"
    assert dist_delhi_mumbai != 5, "Distance must not be fake 5 km!"
    print("PASS: calculate_haversine_distance computes accurate real-world distance")

    # 2. Test Zero Distance for same spot
    dist_self = calculate_haversine_distance(delhi_lat, delhi_lon, delhi_lat, delhi_lon)
    assert dist_self == 0.0
    print("PASS: Same coordinates yield 0.0 km")

    # 3. Test City coordinates lookup
    delhi_coords = get_user_coordinates({"locationName": "Delhi NCR, India"})
    assert delhi_coords is not None
    assert abs(delhi_coords[0] - 28.6139) < 0.01
    print("PASS: City coordinates lookup correctly resolves 'Delhi NCR'")

    mumbai_coords = get_user_coordinates({"locationName": "South Mumbai"})
    assert mumbai_coords is not None
    assert abs(mumbai_coords[0] - 19.0760) < 0.01
    print("PASS: City coordinates lookup correctly resolves 'Mumbai'")

    unknown_coords = get_user_coordinates({"locationName": "Random Nowhere Island"})
    assert unknown_coords is None
    print("PASS: Unknown location without coordinates returns None (no fake assumption)")

    # 4. Test Live GPS override
    live_coords = get_user_coordinates({"locationName": "Delhi NCR"}, query_lat=12.9716, query_lon=77.5946)
    assert live_coords == (12.9716, 77.5946)
    print("PASS: Live query coordinates override city lookup")

    # 5. Test Feed Distance integration in DB
    user_me = {
        "id": "u_test_dist_me",
        "name": "Me User",
        "age": 25,
        "gender": "male",
        "locationName": "Delhi NCR, India",
        "latitude": delhi_lat,
        "longitude": delhi_lon,
    }

    user_mumbai = {
        "id": "u_test_dist_mumbai",
        "name": "Mumbai User",
        "age": 24,
        "gender": "female",
        "locationName": "Mumbai, India",
        "latitude": mumbai_lat,
        "longitude": mumbai_lon,
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample.jpg"],
        "prompts": []
    }

    user_unknown = {
        "id": "u_test_dist_unknown",
        "name": "No GPS User",
        "age": 23,
        "gender": "female",
        "locationName": "Unknown Place",
        "photos": ["https://res.cloudinary.com/demo/image/upload/sample.jpg"],
        "prompts": []
    }

    # Clean previous state
    users_collection.delete_many({"id": {"$in": [user_me["id"], user_mumbai["id"], user_unknown["id"]]}})
    users_collection.insert_one(user_me)
    users_collection.insert_one(user_mumbai)
    users_collection.insert_one(user_unknown)

    try:
        # Fetch discovery feed for user_me
        feed_res = get_discovery_feed(current_user=user_me)
        profiles = {p["id"]: p for p in feed_res["profiles"]}

        assert user_mumbai["id"] in profiles
        mumbai_profile = profiles[user_mumbai["id"]]
        # Must be ~1148 km, NOT 5 km!
        assert mumbai_profile["distanceKm"] is not None
        assert 1140 <= mumbai_profile["distanceKm"] <= 1160
        assert mumbai_profile["distanceKm"] != 5
        print(f"PASS: Mumbai candidate in feed has real distance: {mumbai_profile['distanceKm']} km (not fake 5 km)")

        assert user_unknown["id"] in profiles
        unknown_profile = profiles[user_unknown["id"]]
        # When location cannot be calculated, distanceKm must be None, NOT 5!
        assert unknown_profile["distanceKm"] is None
        print("PASS: Candidate without coordinates returns distanceKm: None (not fake 5 km)")

        # 6. Test Update Location Endpoint
        loc_update = UpdateLocationRequest(latitude=13.0827, longitude=80.2707, locationName="Chennai, India")
        update_res = update_my_location(payload=loc_update, current_user=user_me)
        assert update_res["status"] == "SUCCESS"

        updated_db_user = users_collection.find_one({"id": user_me["id"]})
        assert updated_db_user["latitude"] == 13.0827
        assert updated_db_user["longitude"] == 80.2707
        assert updated_db_user["locationName"] == "Chennai, India"
        assert updated_db_user["location"]["coordinates"] == [80.2707, 13.0827]
        print("PASS: update_my_location updates GPS latitude, longitude, GeoJSON, and city name")

        print("--- ALL DISTANCE CALCULATION TESTS PASSED ---")

    finally:
        users_collection.delete_many({"id": {"$in": [user_me["id"], user_mumbai["id"], user_unknown["id"]]}})

if __name__ == "__main__":
    test_distance_calculation()
