# backend/services/notification_service.py
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson import ObjectId
from database import notifications_collection, users_collection

def create_notification(
    user_id: str,
    notif_type: str,  # "LIKE", "MATCH", "MESSAGE"
    title: str,
    body: str,
    sender_id: Optional[str] = None,
    sender_name: Optional[str] = None,
    sender_photo: Optional[str] = None,
    match_id: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Persists an in-app notification record and returns the created payload.
    """
    now = datetime.utcnow()
    
    # If sender info missing, resolve from sender_id
    if sender_id and (not sender_name or not sender_photo):
        sender = users_collection.find_one({"id": sender_id})
        if sender:
            if not sender_name:
                sender_name = sender.get("name", "Someone")
            if not sender_photo:
                photos = sender.get("photos", [])
                sender_photo = photos[0] if photos else ""

    doc = {
        "user_id": user_id,
        "type": notif_type.upper(),
        "title": title,
        "body": body,
        "sender_id": sender_id,
        "sender_name": sender_name or "Spark Member",
        "sender_photo": sender_photo or "",
        "match_id": match_id,
        "extra_data": extra_data or {},
        "read": False,
        "created_at": now
    }
    
    res = notifications_collection.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["createdAt"] = now.isoformat()
    return doc

def get_user_notifications_summary(user_id: str, limit: int = 30) -> Dict[str, Any]:
    """
    Returns the user's notification feed along with unread badges breakdown:
    - hasUnreadLikes: bool (for small red dot on Likes tab)
    - hasUnreadMatches: bool (for small red dot on Matches/Chats tab)
    - hasUnreadMessages: bool (for small red dot on Chats tab)
    - totalUnread: int
    """
    cursor = notifications_collection.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    
    notifications: List[Dict[str, Any]] = []
    unread_likes = 0
    unread_matches = 0
    unread_messages = 0

    for item in cursor:
        is_read = item.get("read", False)
        n_type = item.get("type", "GENERAL")
        
        if not is_read:
            if n_type == "LIKE":
                unread_likes += 1
            elif n_type == "MATCH":
                unread_matches += 1
            elif n_type == "MESSAGE":
                unread_messages += 1
                
        notifications.append({
            "id": str(item["_id"]),
            "type": n_type,
            "title": item.get("title", ""),
            "body": item.get("body", ""),
            "senderId": item.get("sender_id"),
            "senderName": item.get("sender_name", ""),
            "senderPhoto": item.get("sender_photo", ""),
            "matchId": item.get("match_id"),
            "extraData": item.get("extra_data", {}),
            "read": is_read,
            "createdAt": (item.get("created_at") or datetime.utcnow()).isoformat()
        })

    total_unread = unread_likes + unread_matches + unread_messages

    return {
        "status": "SUCCESS",
        "totalUnread": total_unread,
        "hasUnreadLikes": unread_likes > 0,
        "hasUnreadMatches": unread_matches > 0,
        "hasUnreadMessages": unread_messages > 0,
        "unreadLikesCount": unread_likes,
        "unreadMatchesCount": unread_matches,
        "unreadMessagesCount": unread_messages,
        "notifications": notifications
    }

def mark_user_notifications(
    user_id: str,
    notif_type: Optional[str] = None,
    notif_id: Optional[str] = None
) -> int:
    """
    Marks notifications as read.
    - If notif_id provided, marks that specific notification.
    - If notif_type provided (e.g. 'LIKE', 'MATCH', 'MESSAGE'), marks all of that type.
    - Otherwise marks all notifications for user.
    """
    query: Dict[str, Any] = {"user_id": user_id, "read": False}
    
    if notif_id:
        try:
            query["_id"] = ObjectId(notif_id)
        except Exception:
            return 0
    elif notif_type and notif_type.upper() != "ALL":
        query["type"] = notif_type.upper()

    res = notifications_collection.update_many(query, {"$set": {"read": True, "read_at": datetime.utcnow()}})
    return res.modified_count
