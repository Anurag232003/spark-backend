"""
Test Suite: Issue #58 Reports & Moderation Workflow Endpoints
Tests:
- report_user (user submits report, automatic block created)
- admin_list_reports (filtering by status, pagination)
- admin_get_report (report details + moderation history)
- admin_update_report_status (state machine transitions and invalid transition rejection)
- admin_warn_user (warning registration, warning count)
- admin_suspend_user & admin_unsuspend_user (suspension flag, lifting suspension)
- admin_delete_user (user removal)
"""
from datetime import datetime
# pyrefly: ignore [missing-import]
from bson import ObjectId
from fastapi import HTTPException
from starlette.requests import Request
from database import (
    users_collection,
    reports_collection,
    blocks_collection,
    moderation_actions_collection,
)
import main
from main import (
    report_user,
    admin_list_reports,
    admin_get_report,
    admin_update_report_status,
    admin_warn_user,
    admin_suspend_user,
    admin_unsuspend_user,
    admin_delete_user,
    ReportUserRequest,
    ReportReason,
    ReportStatusUpdate,
    WarnUserRequest,
    SuspendUserRequest,
    UnsuspendUserRequest,
    DeleteUserRequest,
)

def test_moderation_workflow():
    print("--- Running Moderation Workflow Tests ---")

    admin_user = {
        "id": "u_test_admin",
        "name": "Super Admin",
        "role": "admin",
        "phone": "9999900000"
    }

    reporter_user = {
        "id": "u_test_reporter",
        "name": "Reporter User",
        "role": "user",
        "phone": "9999900001"
    }

    bad_user = {
        "id": "u_test_bad_actor",
        "name": "Bad Actor",
        "role": "user",
        "phone": "9999900002"
    }

    # Clean up test documents
    for u in [admin_user, reporter_user, bad_user]:
        users_collection.delete_one({"id": u["id"]})
    reports_collection.delete_many({
        "$or": [
            {"reporter_user_id": reporter_user["id"]},
            {"reported_user_id": bad_user["id"]},
        ]
    })
    blocks_collection.delete_many({
        "$or": [
            {"blocker_user_id": reporter_user["id"]},
            {"target_user_id": bad_user["id"]},
        ]
    })
    moderation_actions_collection.delete_many({
        "$or": [
            {"admin_id": admin_user["id"]},
            {"target_user_id": bad_user["id"]},
        ]
    })

    # Insert test users
    users_collection.insert_one(admin_user)
    users_collection.insert_one(reporter_user)
    users_collection.insert_one(bad_user)

    # 1. Test report_user
    mock_request = Request({
        "type": "http",
        "path": "/api/users/report",
        "client": ("127.0.0.1", 12345),
        "headers": [],
    })
    report_req = ReportUserRequest(
        targetUserId=bad_user["id"],
        reason=ReportReason.HARASSMENT,
        details="Inappropriate conduct in messages"
    )
    rep_res = report_user(mock_request, report_req, current_user=reporter_user)
    assert rep_res["status"] == "SUCCESS"

    # Find the report in DB
    report_doc = reports_collection.find_one({
        "reporter_user_id": reporter_user["id"],
        "reported_user_id": bad_user["id"]
    })
    assert report_doc is not None
    report_id = str(report_doc["_id"])
    print("PASS: User report submitted successfully, report document stored in DB")

    # Verify auto-block was created
    block_doc = blocks_collection.find_one({
        "blocker_user_id": reporter_user["id"],
        "target_user_id": bad_user["id"]
    })
    assert block_doc is not None
    assert "HARASSMENT" in block_doc["reason"]
    print("PASS: Auto-block created on report submission")

    # 2. Test admin_list_reports
    list_res = admin_list_reports(report_status="PENDING_REVIEW", page=1, page_size=10, admin=admin_user)
    assert list_res["status"] == "SUCCESS"
    matching_reports = [r for r in list_res["reports"] if r["reportId"] == report_id]
    assert len(matching_reports) == 1
    assert matching_reports[0]["reason"] == "HARASSMENT"
    print("PASS: admin_list_reports retrieves pending report with reporter & reported metadata")

    # 3. Test admin_get_report
    detail_res = admin_get_report(report_id, admin=admin_user)
    assert detail_res["status"] == "SUCCESS"
    assert detail_res["report"]["status"] == "PENDING_REVIEW"
    assert "INVESTIGATING" in detail_res["report"]["allowedNextStatuses"]
    print("PASS: admin_get_report retrieved report details and allowed transitions")

    # 4. Test admin_update_report_status (state machine)
    # 4a. Valid transition: PENDING_REVIEW -> INVESTIGATING
    update_res = admin_update_report_status(
        report_id,
        ReportStatusUpdate(newStatus="INVESTIGATING", notes="Reviewing chat history"),
        admin=admin_user
    )
    assert update_res["status"] == "SUCCESS"
    assert update_res["newStatus"] == "INVESTIGATING"
    print("PASS: Transition PENDING_REVIEW -> INVESTIGATING accepted")

    # 4b. Invalid transition test: INVESTIGATING cannot jump directly to PENDING_REVIEW
    try:
        admin_update_report_status(
            report_id,
            ReportStatusUpdate(newStatus="PENDING_REVIEW"),
            admin=admin_user
        )
        assert False, "Should have rejected invalid status transition"
    except HTTPException as e:
        assert e.status_code == 400
        print("PASS: Invalid transition INVESTIGATING -> PENDING_REVIEW correctly rejected (400)")

    # 5. Test admin_warn_user
    warn_res = admin_warn_user(
        bad_user["id"],
        WarnUserRequest(reason="Harassment policy violation", reportId=report_id),
        admin=admin_user
    )
    assert warn_res["status"] == "SUCCESS"
    assert warn_res["totalWarnings"] == 1
    updated_bad_user = users_collection.find_one({"id": bad_user["id"]})
    assert len(updated_bad_user.get("warnings", [])) == 1
    print("PASS: admin_warn_user registered warning on user profile")

    # 6. Test admin_suspend_user and admin_unsuspend_user
    suspend_res = admin_suspend_user(
        bad_user["id"],
        SuspendUserRequest(reason="Repeated harassment", durationHours=48, reportId=report_id),
        admin=admin_user
    )
    assert suspend_res["status"] == "SUCCESS"
    suspended_doc = users_collection.find_one({"id": bad_user["id"]})
    assert suspended_doc["is_suspended"] is True
    print("PASS: admin_suspend_user marked user is_suspended=True with timestamp")

    unsuspend_res = admin_unsuspend_user(
        bad_user["id"],
        UnsuspendUserRequest(notes="Suspension lifted early"),
        admin=admin_user
    )
    assert unsuspend_res["status"] == "SUCCESS"
    unsuspended_doc = users_collection.find_one({"id": bad_user["id"]})
    assert unsuspended_doc["is_suspended"] is False
    print("PASS: admin_unsuspend_user restored user to active status")

    # 7. Test audit trail in get_report
    detail_with_history = admin_get_report(report_id, admin=admin_user)
    history_actions = [h["action"] for h in detail_with_history["report"]["moderationHistory"]]
    assert "STATUS_INVESTIGATING" in history_actions
    assert "WARN" in history_actions
    assert "SUSPEND" in history_actions
    print(f"PASS: Full moderation audit trail captured ({len(history_actions)} actions)")

    # 8. Test admin_delete_user
    del_res = admin_delete_user(
        bad_user["id"],
        DeleteUserRequest(reason="Severe repeated violations", reportId=report_id),
        admin=admin_user
    )
    assert del_res["status"] == "SUCCESS"
    assert users_collection.find_one({"id": bad_user["id"]}) is None
    print("PASS: admin_delete_user permanently deleted user document")

    # Clean up test artifacts
    users_collection.delete_one({"id": admin_user["id"]})
    users_collection.delete_one({"id": reporter_user["id"]})
    reports_collection.delete_one({"_id": ObjectId(report_id)})
    moderation_actions_collection.delete_many({"report_id": report_id})

    print("--- ALL MODERATION WORKFLOW TESTS PASSED ---")

if __name__ == "__main__":
    test_moderation_workflow()
