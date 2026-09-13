# backend/services/safety_service.py
"""
Spark Date Safety Center Service — India-First Safety Hub
Provides Trusted Contacts management, Date Check-in timer with safety confirmation,
and official Indian emergency resources.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from database import trusted_contacts_collection, date_checkins_collection

# National Indian Emergency Hotlines & Verified Resources
INDIA_SAFETY_RESOURCES = {
    "hotlines": [
        {
            "id": "112",
            "name": "National Emergency Hotline",
            "number": "112",
            "category": "Police, Fire, Ambulance",
            "desc": "Single emergency response number across all states in India.",
            "available": "24x7 Free",
        },
        {
            "id": "1091",
            "name": "Women's Emergency Helpline",
            "number": "1091",
            "category": "Women Safety",
            "desc": "Dedicated 24x7 police response for women in distress.",
            "available": "24x7 Free",
        },
        {
            "id": "1930",
            "name": "National Cyber Crime Helpline",
            "number": "1930",
            "category": "Financial & Romance Fraud",
            "desc": "Immediate reporting for online scams, extortion, and UPI fraud.",
            "available": "24x7 Free",
        },
        {
            "id": "100",
            "name": "Police Helpline",
            "number": "100",
            "category": "Police",
            "desc": "Direct local police dispatch.",
            "available": "24x7 Free",
        },
    ],
    "scamGuides": [
        {
            "id": "cafe_bill_scam",
            "title": "Delhi/Mumbai Cafe Bill Scam 🍷",
            "riskLevel": "HIGH",
            "summary": "Dates at newly opened or secluded cafes where the bill is inflated to ₹20,000–₹60,000.",
            "signs": [
                "The match insists on going to a specific unknown cafe/lounge.",
                "They order premium drinks without asking you or checking menu prices.",
                "Bouncers demand immediate UPI or cash payment.",
            ],
            "advice": "Always propose popular, well-reviewed public places (e.g. Starbucks, Third Wave, CCD, known malls) for first dates. If in doubt, ask to split or check prices before ordering.",
        },
        {
            "id": "upi_qr_scam",
            "title": "UPI 'Receive Money' QR Scam 💳",
            "riskLevel": "CRITICAL",
            "summary": "Scammer claims they are sending you money, but sends a PIN/QR request that actually deducts funds.",
            "signs": [
                "Asking you to scan a QR code to 'receive' payment or gift.",
                "Claiming their UPI is blocked and asking for a temporary transfer.",
                "Sharing fake screenshots of pending transfers.",
            ],
            "advice": "NEVER enter your UPI PIN to receive money. UPI PIN is only needed to send money. Never send money to someone you have not met in person.",
        },
        {
            "id": "parcel_customs_scam",
            "title": "Customs Duty & Gift Parcel Scam 🎁",
            "riskLevel": "HIGH",
            "summary": "Match claims to be an NRI, pilot, or overseas engineer sending an expensive gift or jewelry.",
            "signs": [
                "Claims a valuable package has been detained by Indian Customs at Delhi or Mumbai airport.",
                "You receive calls or WhatsApp messages demanding 'clearance duty' or 'tax payment'.",
            ],
            "advice": "Customs never calls individuals demanding UPI transfers to personal accounts. Block immediately and report to 1930.",
        },
        {
            "id": "sextortion_scam",
            "title": "Video Call Blackmail (Sextortion) 📵",
            "riskLevel": "CRITICAL",
            "summary": "Scammer quickly pushes to switch to WhatsApp/Telegram video call, then records and blackmails.",
            "signs": [
                "Pressure to move off-app immediately.",
                "Urging you to turn on camera in private or undress.",
                "Threats to leak recorded screen captures to your social media contacts.",
            ],
            "advice": "Never engage in compromising video calls with strangers. If blackmailed, DO NOT pay (they always ask for more). Immediately file a complaint at cybercrime.gov.in and dial 1930.",
        },
    ],
}


def get_trusted_contacts(user_id: str) -> List[Dict[str, Any]]:
    """Fetches all saved trusted emergency contacts for a user."""
    doc = trusted_contacts_collection.find_one({"user_id": user_id})
    if not doc or "contacts" not in doc:
        return []
    return doc.get("contacts", [])


def save_trusted_contact(user_id: str, contact_data: Dict[str, Any]) -> Dict[str, Any]:
    """Adds or updates a trusted emergency contact."""
    contact_id = contact_data.get("id") or f"tc_{uuid.uuid4().hex[:8]}"
    name = (contact_data.get("name") or "").strip()
    phone = (contact_data.get("phone") or "").strip()
    relationship = (contact_data.get("relationship") or "Friend").strip()
    is_primary = bool(contact_data.get("isPrimary", False))

    if not name or not phone:
        raise ValueError("Contact name and phone number are required.")

    new_contact = {
        "id": contact_id,
        "name": name,
        "phone": phone,
        "relationship": relationship,
        "isPrimary": is_primary,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    doc = trusted_contacts_collection.find_one({"user_id": user_id})
    if not doc:
        trusted_contacts_collection.insert_one({
            "user_id": user_id,
            "contacts": [new_contact],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        existing_contacts = doc.get("contacts", [])
        # If updating existing
        replaced = False
        updated_list = []
        for c in existing_contacts:
            if c.get("id") == contact_id:
                updated_list.append(new_contact)
                replaced = True
            else:
                # If new contact is primary, unmark previous primary
                if is_primary:
                    c["isPrimary"] = False
                updated_list.append(c)

        if not replaced:
            if len(existing_contacts) >= 5:
                raise ValueError("Maximum 5 trusted contacts allowed.")
            if is_primary:
                for c in updated_list:
                    c["isPrimary"] = False
            updated_list.append(new_contact)

        trusted_contacts_collection.update_one(
            {"user_id": user_id},
            {"$set": {"contacts": updated_list, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

    return new_contact


def delete_trusted_contact(user_id: str, contact_id: str) -> bool:
    """Removes a trusted contact for a user."""
    doc = trusted_contacts_collection.find_one({"user_id": user_id})
    if not doc:
        return False

    contacts = doc.get("contacts", [])
    filtered = [c for c in contacts if c.get("id") != contact_id]

    if len(filtered) == len(contacts):
        return False

    trusted_contacts_collection.update_one(
        {"user_id": user_id},
        {"$set": {"contacts": filtered, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return True


def start_date_checkin(
    user_id: str,
    match_id: Optional[str] = None,
    partner_name: str = "Date Partner",
    location_name: str = "Cafe / Public place",
    duration_minutes: int = 120,
) -> Dict[str, Any]:
    """Starts an active safety check-in countdown timer for an in-person date."""
    # Complete any previously active checkin
    date_checkins_collection.update_many(
        {"user_id": user_id, "status": "ACTIVE"},
        {"$set": {"status": "SUPERSEDED", "completed_at": datetime.now(timezone.utc).isoformat()}}
    )

    checkin_id = f"chk_{uuid.uuid4().hex[:10]}"
    start_time = datetime.now(timezone.utc)
    deadline = start_time + timedelta(minutes=duration_minutes)

    checkin_doc = {
        "checkin_id": checkin_id,
        "user_id": user_id,
        "match_id": match_id or "",
        "partner_name": partner_name,
        "location_name": location_name,
        "duration_minutes": duration_minutes,
        "start_time": start_time.isoformat(),
        "checkin_deadline": deadline.isoformat(),
        "status": "ACTIVE",
        "created_at": start_time.isoformat(),
    }

    date_checkins_collection.insert_one(checkin_doc)
    checkin_doc.pop("_id", None)
    return checkin_doc


def update_date_checkin_status(user_id: str, checkin_id: str, status: str) -> Dict[str, Any]:
    """Updates status (e.g. COMPLETED_SAFE, SOS_TRIGGERED)."""
    valid_statuses = ["ACTIVE", "COMPLETED_SAFE", "SOS_TRIGGERED", "CANCELLED"]
    if status not in valid_statuses:
        raise ValueError(f"Invalid status. Must be one of {valid_statuses}")

    now = datetime.now(timezone.utc).isoformat()
    res = date_checkins_collection.find_one_and_update(
        {"user_id": user_id, "checkin_id": checkin_id},
        {"$set": {"status": status, "updated_at": now}},
        return_document=True
    )

    if not res:
        raise ValueError("Date check-in record not found.")

    res.pop("_id", None)
    return res


def get_active_date_checkin(user_id: str) -> Optional[Dict[str, Any]]:
    """Returns the currently active date checkin if any."""
    doc = date_checkins_collection.find_one(
        {"user_id": user_id, "status": "ACTIVE"},
        sort=[("created_at", -1)]
    )
    if not doc:
        return None
    doc.pop("_id", None)
    return doc
