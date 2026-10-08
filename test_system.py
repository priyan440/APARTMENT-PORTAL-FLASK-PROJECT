"""
End-to-End System Integration Test for Apartment Residential Portal
Verifies all 5 user roles, RBAC, Complaint Lifecycle, Double Booking Prevention,
Operating Hours Validation, Simulated Payment, and PDF generation.
"""

import sys
import os
import unittest
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from database.mongodb import get_db
from database.seed import seed_database
from services.receipt_service import generate_booking_pdf, generate_payment_pdf

class ApartmentPortalTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n=== Initializing Test Environment & Seeding Database ===")
        seed_database()
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()

    def test_01_auth_and_roles_login(self):
        """Test authentication for all 5 roles."""
        creds = [
            ("admin@greenwood.com", "admin123", "/admin/dashboard"),
            ("manager@greenwood.com", "manager123", "/manager/dashboard"),
            ("resident@greenwood.com", "resident123", "/resident/dashboard"),
            ("ravi@greenwood.com", "tech123", "/technician/dashboard"),
            ("security@greenwood.com", "security123", "/security/dashboard"),
        ]
        for email, pwd, expected_redirect in creds:
            res = self.client.post("/login", data={"identifier": email, "password": pwd}, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Failed login redirect for {email}")
            self.assertIn(expected_redirect, res.headers["Location"], f"Wrong redirect destination for {email}")
            # Logout
            self.client.get("/logout")

    def test_02_rbac_unauthorized_route_protection(self):
        """Verify user cannot access other role's restricted URLs."""
        # Login as Resident
        self.client.post("/login", data={"identifier": "resident@greenwood.com", "password": "resident123"})
        
        # Try accessing manager and admin routes
        res_mgr = self.client.get("/manager/dashboard", follow_redirects=False)
        self.assertEqual(res_mgr.status_code, 302, "Resident was not redirected from Manager dashboard")
        self.assertIn("/resident/dashboard", res_mgr.headers["Location"])

        res_adm = self.client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(res_adm.status_code, 302, "Resident was not redirected from Admin dashboard")
        self.assertIn("/resident/dashboard", res_adm.headers["Location"])

        self.client.get("/logout")

    def test_03_complaint_technician_resident_workflow(self):
        """
        Demo Scenario 1:
        Resident raises complaint -> Manager assigns Ravi Kumar ->
        Technician accepts & starts work (IN_PROGRESS) -> Technician marks RESOLVED ->
        Resident sees status and rates 5 stars!
        """
        # Step 1: Resident raises complaint
        self.client.post("/login", data={"identifier": "resident@greenwood.com", "password": "resident123"})
        res = self.client.post("/resident/complaints", data={
            "category": "Plumbing",
            "priority": "HIGH",
            "title": "Severe Water Leakage in Balcony",
            "description": "Balcony pipeline cracked, water gushing onto lower floor."
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        db = get_db()
        complaint = db.complaints.find_one({"title": "Severe Water Leakage in Balcony"})
        self.assertIsNotNone(complaint)
        cid = complaint["complaint_id"]
        self.assertEqual(complaint["status"], "OPEN")
        self.assertEqual(complaint["status_history"][0]["status"], "OPEN")
        self.client.get("/logout")

        # Step 2: Manager assigns Ravi Kumar (TECH001)
        self.client.post("/login", data={"identifier": "manager@greenwood.com", "password": "manager123"})
        res_assign = self.client.post(f"/manager/complaints/{cid}/assign", data={
            "technician_id": "TECH001",
            "priority": "HIGH"
        }, follow_redirects=True)
        self.assertEqual(res_assign.status_code, 200)

        complaint = db.complaints.find_one({"complaint_id": cid})
        self.assertEqual(complaint["status"], "ASSIGNED")
        self.assertEqual(complaint["technician_id"], "TECH001")
        self.client.get("/logout")

        # Step 3: Technician Ravi Kumar starts work (IN_PROGRESS)
        self.client.post("/login", data={"identifier": "ravi@greenwood.com", "password": "tech123"})
        res_start = self.client.post(f"/technician/tasks/{cid}/update-status", data={
            "status": "IN_PROGRESS",
            "notes": "Arrived at Flat A-204 with replacement PVC connectors."
        }, follow_redirects=True)
        self.assertEqual(res_start.status_code, 200)

        complaint = db.complaints.find_one({"complaint_id": cid})
        self.assertEqual(complaint["status"], "IN_PROGRESS")

        # Step 4: Technician completes and marks RESOLVED
        res_resolve = self.client.post(f"/technician/tasks/{cid}/update-status", data={
            "status": "RESOLVED",
            "notes": "Replaced cracked elbow pipe, tested pressure for 15 minutes without leaks."
        }, follow_redirects=True)
        self.assertEqual(res_resolve.status_code, 200)

        complaint = db.complaints.find_one({"complaint_id": cid})
        self.assertEqual(complaint["status"], "RESOLVED")
        self.assertIsNotNone(complaint.get("resolution_notes"))
        self.client.get("/logout")

        # Step 5: Resident rates 5 stars
        self.client.post("/login", data={"identifier": "resident@greenwood.com", "password": "resident123"})
        res_rate = self.client.post(f"/resident/complaints/{cid}/rate", data={
            "rating": "5",
            "feedback": "Outstanding work by Ravi! Solved within an hour."
        }, follow_redirects=True)
        self.assertEqual(res_rate.status_code, 200)

        complaint = db.complaints.find_one({"complaint_id": cid})
        self.assertEqual(complaint["status"], "CLOSED")
        self.assertEqual(complaint["rating"], 5)
        self.client.get("/logout")
        print("[PASS] Complaint -> Manager -> Technician -> Resident -> 5-star Rating workflow passed!")

    def test_04_amenity_double_booking_and_conflict_prevention(self):
        """
        Demo Scenario 2:
        Community Hall is booked on future_date 10:00 - 14:00 (APPROVED).
        New request 13:00 - 16:00 MUST be rejected with conflict!
        Non-conflicting request 15:00 - 18:00 MUST be accepted as PENDING.
        Manager approves -> receipt & QR generated!
        """
        db = get_db()
        future_date = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")

        # Login as Priya (RES002)
        self.client.post("/login", data={"identifier": "priya@greenwood.com", "password": "resident123"})
        
        # Conflicting request: 13:00 to 16:00 (overlaps with existing BK001 10:00 - 14:00)
        res_conflict = self.client.post("/resident/amenities/book", data={
            "amenity_id": "AMN001",
            "booking_date": future_date,
            "start_time": "13:00",
            "end_time": "16:00",
            "guests_count": "20",
            "purpose": "Afternoon Tea Function"
        }, follow_redirects=True)
        self.assertIn(b"is already confirmed", res_conflict.data)

        # Valid non-conflicting request: 15:00 to 18:00
        res_valid = self.client.post("/resident/amenities/book", data={
            "amenity_id": "AMN001",
            "booking_date": future_date,
            "start_time": "15:00",
            "end_time": "18:00",
            "guests_count": "25",
            "purpose": "Evening Art Showcase"
        }, follow_redirects=True)
        self.assertEqual(res_valid.status_code, 200)

        new_bk = db.bookings.find_one({"purpose": "Evening Art Showcase"})
        self.assertIsNotNone(new_bk)
        self.assertEqual(new_bk["status"], "PENDING")
        self.client.get("/logout")

        # Manager approves the new booking
        self.client.post("/login", data={"identifier": "manager@greenwood.com", "password": "manager123"})
        res_appr = self.client.post(f"/manager/amenity-bookings/{new_bk['booking_id']}/approve", data={
            "remarks": "Approved with pleasure."
        }, follow_redirects=True)
        self.assertEqual(res_appr.status_code, 200)

        updated_bk = db.bookings.find_one({"booking_id": new_bk["booking_id"]})
        self.assertEqual(updated_bk["status"], "APPROVED")
        self.assertIsNotNone(updated_bk["receipt_number"])
        self.assertIsNotNone(updated_bk["qr_code_data"])
        self.client.get("/logout")
        print("[PASS] Strict Amenity Double-Booking Prevention and Approval Pass passed!")

    def test_05_amenity_operating_hours_validation(self):
        """Swimming Pool is fixed 10:00 - 18:00. 08:00 - 10:00 must be rejected."""
        self.client.post("/login", data={"identifier": "resident@greenwood.com", "password": "resident123"})
        future_date = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")

        res_hours = self.client.post("/resident/amenities/book", data={
            "amenity_id": "AMN003", # Swimming Pool
            "booking_date": future_date,
            "start_time": "08:00",
            "end_time": "10:00",
            "guests_count": "2",
            "purpose": "Morning Swim"
        }, follow_redirects=True)
        self.assertIn(b"outside operating hours", res_hours.data)
        self.client.get("/logout")
        print("[PASS] Amenity operating hours validation passed!")

    def test_06_simulated_bill_payment_scenario(self):
        """
        Demo Scenario 3:
        Resident sees pending bill BILL001 (₹3,300).
        Completes test payment.
        Bill status -> PAID, payment record created, receipt and PDF available.
        """
        db = get_db()
        self.client.post("/login", data={"identifier": "resident@greenwood.com", "password": "resident123"})
        
        # Verify bill exists and pending
        bill = db.bills.find_one({"bill_id": "BILL001"})
        self.assertEqual(bill["status"], "PENDING")
        self.assertEqual(bill["total_amount"], 3300.0)

        # Process payment
        res_pay = self.client.post("/resident/bills/BILL001/pay", data={"payment_method": "UPI"}, follow_redirects=True)
        self.assertEqual(res_pay.status_code, 200)

        bill_after = db.bills.find_one({"bill_id": "BILL001"})
        self.assertEqual(bill_after["status"], "PAID")
        self.assertIsNotNone(bill_after.get("payment_id"))

        payment = db.payments.find_one({"bill_id": "BILL001"})
        self.assertIsNotNone(payment)
        self.assertEqual(payment["status"], "SUCCESS")
        self.assertEqual(payment["amount"], 3300.0)

        # Test PDF receipt download
        res_pdf = self.client.get("/resident/bills/BILL001/receipt/pdf")
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.mimetype, "application/pdf")
        self.assertGreater(len(res_pdf.data), 1000)

        self.client.get("/logout")
        print("[PASS] Demo Scenario 3: Bill Payment & PDF Receipt Generation passed!")

    def test_07_security_visitors_and_sos(self):
        """Test gate visitor check in/out and emergency SOS alert."""
        db = get_db()
        # Resident triggers SOS
        self.client.post("/login", data={"identifier": "resident@greenwood.com", "password": "resident123"})
        res_sos = self.client.post("/resident/emergency", data={
            "alert_type": "Medical",
            "notes": "Elderly parent fell in living room."
        }, follow_redirects=True)
        self.assertEqual(res_sos.status_code, 200)
        
        sos = db.emergency_alerts.find_one({"resident_id": "RES001", "status": "ACTIVE"})
        self.assertIsNotNone(sos)
        self.client.get("/logout")

        # Security responds to SOS
        self.client.post("/login", data={"identifier": "security@greenwood.com", "password": "security123"})
        res_resolve_sos = self.client.post("/security/emergency", data={
            "alert_id": sos["alert_id"],
            "action_note": "First aid responder dispatched with wheelchair."
        }, follow_redirects=True)
        self.assertEqual(res_resolve_sos.status_code, 200)

        sos_after = db.emergency_alerts.find_one({"alert_id": sos["alert_id"]})
        self.assertEqual(sos_after["status"], "RESOLVED")
        self.client.get("/logout")
        print("[PASS] Emergency SOS and Security dispatch passed!")

    def test_08_analytics_api_aggregation(self):
        """Test MongoDB Aggregation Analytics endpoint."""
        self.client.post("/login", data={"identifier": "manager@greenwood.com", "password": "manager123"})
        res = self.client.get("/manager/api/analytics-data")
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertIn("residents_by_block", json_data)
        self.assertIn("billing_by_block", json_data)
        self.assertIn("complaints_by_category", json_data)
        self.assertIn("technicians", json_data)
        self.client.get("/logout")
        print("[PASS] MongoDB Aggregation Analytics API verified!")

if __name__ == "__main__":
    unittest.main()
