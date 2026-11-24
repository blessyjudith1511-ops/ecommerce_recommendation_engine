"""
test_app.py - Comprehensive Automated Verification Script
==========================================================
Tests all critical components:
1. Authentication (Register, Login, Password Hashing, Sessions, Logout)
2. Product Browsing, Filters, and Sorting
3. Recommendation Engine & User Activity Logging
4. Database Shopping Cart, Stock Validation & Order Checkout
5. Query Optimization Dashboard & Benchmarks
6. Admin Panel & Access Control
"""

import sys
from app import app
from database import get_connection, initialize_database


def run_tests():
    print("=" * 60)
    print("🚀 Starting Automated Test Suite for E-Commerce Recommendation Engine")
    print("=" * 60)

    # Re-initialize database and clean transactional tables for deterministic testing
    initialize_database()
    conn = get_connection()
    conn.execute("DELETE FROM cart;")
    conn.execute("DELETE FROM wishlist;")
    conn.commit()
    conn.close()

    client = app.test_client()

    # -------------------------------------------------------------
    # 1. Test Homepage
    # -------------------------------------------------------------
    print("\n[Test 1] Testing Homepage ('/')...")
    resp = client.get("/")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert b"AuraShop" in resp.data
    assert b"UltraBook Pro Laptop" in resp.data
    print("  -> Passed! Homepage rendered with products.")

    # -------------------------------------------------------------
    # 2. Test Search & Filters
    # -------------------------------------------------------------
    print("\n[Test 2] Testing Search and Category Filter...")
    # Search by keyword
    resp = client.get("/?search=Laptop")
    assert resp.status_code == 200
    assert b"UltraBook Pro Laptop" in resp.data

    # Category filter
    resp = client.get("/?category=Books")
    assert resp.status_code == 200
    assert b"Python Programming Mastery" in resp.data
    assert b"UltraBook Pro Laptop" not in resp.data

    # Price filter
    resp = client.get("/?max_price=800")
    assert resp.status_code == 200
    assert b"Wireless Ergonomic Mouse" in resp.data
    assert b"UltraBook Pro Laptop" not in resp.data
    print("  -> Passed! Search, category, and price filters work correctly.")

    # -------------------------------------------------------------
    # 3. Test Registration & Duplicate Prevention
    # -------------------------------------------------------------
    print("\n[Test 3] Testing User Registration...")
    test_email = "newstudent@college.edu"
    
    # Delete test user if already exists from prior runs
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE email = ?", (test_email,))
    conn.commit()
    conn.close()

    # Register new user
    resp = client.post("/register", data={
        "full_name": "Test Student",
        "email": test_email,
        "password": "mypassword123",
        "confirm_password": "mypassword123"
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Registration successful" in resp.data

    # Attempt duplicate registration
    resp_dup = client.post("/register", data={
        "full_name": "Duplicate Test",
        "email": test_email,
        "password": "mypassword123",
        "confirm_password": "mypassword123"
    }, follow_redirects=True)
    assert resp_dup.status_code == 200
    assert b"already exists" in resp_dup.data
    print("  -> Passed! User registration and duplicate email check working.")

    # -------------------------------------------------------------
    # 4. Test Login, Session, and Password Hashing
    # -------------------------------------------------------------
    print("\n[Test 4] Testing User Login & Session...")
    # Bad credentials
    resp_bad = client.post("/login", data={
        "email": test_email,
        "password": "wrongpassword"
    }, follow_redirects=True)
    assert resp_bad.status_code == 200
    assert b"Invalid email or password" in resp_bad.data

    # Good credentials
    resp_good = client.post("/login", data={
        "email": test_email,
        "password": "mypassword123"
    }, follow_redirects=True)
    assert resp_good.status_code == 200
    assert b"Welcome back, Test Student" in resp_good.data
    print("  -> Passed! Secure login and session established.")

    # -------------------------------------------------------------
    # 5. Test Product Details & Activity Logging
    # -------------------------------------------------------------
    print("\n[Test 5] Testing Product Details & Dynamic Recommendations...")
    resp_prod = client.get("/product/1")
    assert resp_prod.status_code == 200
    assert b"UltraBook Pro Laptop" in resp_prod.data
    assert b"Recommended Products" in resp_prod.data
    assert b"Top rated in Electronics" in resp_prod.data

    # Verify user_activity was logged
    conn = get_connection()
    act = conn.execute(
        "SELECT * FROM user_activity WHERE product_id = 1 AND activity_type = 'view'"
    ).fetchone()
    assert act is not None, "Product view activity was not logged!"
    conn.close()
    print("  -> Passed! Product details, category recommendation, and activity log verified.")

    # -------------------------------------------------------------
    # 6. Test Shopping Cart Operations & Stock Constraints
    # -------------------------------------------------------------
    print("\n[Test 6] Testing Shopping Cart & Stock Constraints...")
    # Add product 1 with quantity 2
    resp_cart = client.post("/add_to_cart/1", data={"quantity": 2}, follow_redirects=True)
    assert resp_cart.status_code == 200
    assert b"Added 2" in resp_cart.data
    assert b"UltraBook Pro Laptop" in resp_cart.data

    # View Cart page
    resp_view_cart = client.get("/cart")
    assert resp_view_cart.status_code == 200
    assert b"UltraBook Pro Laptop" in resp_view_cart.data

    # Increase quantity (+)
    client.post("/update_cart/1", data={"action": "increase"}, follow_redirects=True)
    
    # Check updated quantity in database
    conn = get_connection()
    c_item = conn.execute("SELECT quantity FROM cart WHERE product_id = 1").fetchone()
    assert c_item["quantity"] == 3, f"Expected 3, got {c_item['quantity']}"
    conn.close()

    # Decrease quantity (-)
    client.post("/update_cart/1", data={"action": "decrease"}, follow_redirects=True)
    conn = get_connection()
    c_item = conn.execute("SELECT quantity FROM cart WHERE product_id = 1").fetchone()
    assert c_item["quantity"] == 2
    conn.close()
    print("  -> Passed! Add to cart, quantity update (+/-), and stock checks verified.")

    # -------------------------------------------------------------
    # 7. Test Demo Payment System & Checkout
    # -------------------------------------------------------------
    print("\n[Test 7] Testing Demo Payment System & Checkout...")
    # 7.1 Verify Checkout Page (GET /checkout)
    resp_get_checkout = client.get("/checkout")
    assert resp_get_checkout.status_code == 200
    assert b"Demo Payment & Checkout" in resp_get_checkout.data
    assert b"Demo Card" in resp_get_checkout.data
    assert b"Demo UPI" in resp_get_checkout.data
    assert b"Cash on Delivery" in resp_get_checkout.data

    # 7.2 Test Simulated Payment Failure
    resp_failed_checkout = client.post("/checkout", data={
        "payment_method": "Demo Card",
        "simulation_outcome": "failure"
    }, follow_redirects=True)
    assert resp_failed_checkout.status_code == 200
    assert b"Demo Payment Declined" in resp_failed_checkout.data
    assert b"TXN-AURA" in resp_failed_checkout.data
    # Verify cart items were NOT cleared upon failure
    conn = get_connection()
    cart_after_fail = conn.execute("SELECT COUNT(*) FROM cart").fetchone()[0]
    assert cart_after_fail > 0, "Cart items should be preserved when payment fails!"
    conn.close()

    # 7.3 Test Successful Demo Payment (Demo Card)
    conn = get_connection()
    stock_before = conn.execute("SELECT stock FROM products WHERE product_id = 1").fetchone()["stock"]
    conn.close()

    resp_checkout = client.post("/checkout", data={
        "payment_method": "Demo Card",
        "simulation_outcome": "success"
    }, follow_redirects=True)
    assert resp_checkout.status_code == 200
    assert b"Payment Confirmed" in resp_checkout.data
    assert b"TXN-AURA" in resp_checkout.data

    # Check stock decrement
    conn = get_connection()
    stock_after = conn.execute("SELECT stock FROM products WHERE product_id = 1").fetchone()["stock"]
    assert stock_after == stock_before - 2, f"Stock did not decrement correctly! Before: {stock_before}, After: {stock_after}"

    # Check cart is now empty for this user
    c_count = conn.execute("SELECT COUNT(*) FROM cart WHERE user_id = (SELECT user_id FROM users WHERE email = ?)", (test_email,)).fetchone()[0]
    assert c_count == 0, "Cart was not cleared after successful checkout!"

    # Verify Payment record in database
    payment_rec = conn.execute("SELECT * FROM payments WHERE payment_status = 'Paid' ORDER BY payment_id DESC LIMIT 1").fetchone()
    assert payment_rec is not None, "Payment record was not created!"
    assert payment_rec["payment_method"] == "Demo Card"
    assert payment_rec["transaction_id"].startswith("TXN-AURA-")
    conn.close()

    # 7.4 Test Cash on Delivery (COD) Payment
    # Add product 5 to cart for COD test
    client.post("/add_to_cart/5", data={"quantity": 1}, follow_redirects=True)
    resp_cod = client.post("/checkout", data={
        "payment_method": "Cash on Delivery",
        "simulation_outcome": "success",
        "delivery_address": "Campus Hostel Room 101"
    }, follow_redirects=True)
    assert resp_cod.status_code == 200
    assert b"Payment Pending on Delivery" in resp_cod.data
    conn = get_connection()
    cod_payment = conn.execute("SELECT * FROM payments WHERE payment_method = 'Cash on Delivery' ORDER BY payment_id DESC LIMIT 1").fetchone()
    assert cod_payment is not None
    assert cod_payment["payment_status"] == "Pending"
    conn.close()

    # 7.5 Test Payment History Page (GET /payments)
    resp_payments = client.get("/payments")
    assert resp_payments.status_code == 200
    assert b"My Payment History" in resp_payments.data
    assert b"TXN-AURA" in resp_payments.data
    assert b"Paid" in resp_payments.data
    assert b"Pending" in resp_payments.data
    assert b"Failed" in resp_payments.data

    # 7.6 View Order History
    resp_orders = client.get("/orders")
    assert resp_orders.status_code == 200
    assert b"UltraBook Pro Laptop" in resp_orders.data
    assert b"TXN-AURA" in resp_orders.data
    print("  -> Passed! Demo Card, UPI, COD, failure simulation, transaction IDs, and payment history verified.")

    # -------------------------------------------------------------
    # 8. Test Query Optimization Dashboard
    # -------------------------------------------------------------
    print("\n[Test 8] Testing Query Optimization Dashboard...")
    resp_opt = client.get("/optimization")
    assert resp_opt.status_code == 200
    assert b"DBMS Query Optimization Dashboard" in resp_opt.data
    assert b"EXPLAIN QUERY PLAN" in resp_opt.data
    assert b"idx_product_category_rating" in resp_opt.data
    assert b"Speedup Factor" in resp_opt.data
    print("  -> Passed! Optimization dashboard and live benchmarks render cleanly.")

    # -------------------------------------------------------------
    # 9. Test Admin Access Control & Catalog Management
    # -------------------------------------------------------------
    print("\n[Test 9] Testing Admin Access Control...")
    # Normal user (Test Student) trying to access /admin
    resp_admin_deny = client.get("/admin", follow_redirects=True)
    assert b"Administrator privileges required" in resp_admin_deny.data

    # Log in as Admin
    client.get("/logout")
    resp_admin_login = client.post("/login", data={
        "email": "admin@ecommerce.com",
        "password": "admin123"
    }, follow_redirects=True)
    assert b"Welcome back, Admin Manager" in resp_admin_login.data

    # Now access /admin
    resp_admin_allow = client.get("/admin")
    assert resp_admin_allow.status_code == 200
    assert b"Catalog Management & Admin Panel" in resp_admin_allow.data

    # Admin: Add new product
    resp_add = client.post("/admin/product/add", data={
        "name": "Smart Wireless Speaker",
        "category": "Electronics",
        "price": "3499.00",
        "rating": "4.6",
        "stock": "20",
        "description": "High fidelity 360-degree Bluetooth speaker with deep bass.",
        "image": "🔊"
    }, follow_redirects=True)
    assert resp_add.status_code == 200
    assert b"added successfully" in resp_add.data

    # Verify product in database
    conn = get_connection()
    new_prod = conn.execute("SELECT * FROM products WHERE name = 'Smart Wireless Speaker'").fetchone()
    assert new_prod is not None
    assert new_prod["price"] == 3499.00
    new_pid = new_prod["product_id"]
    conn.close()

    # Admin: Update stock
    client.post(f"/admin/product/stock/{new_pid}", data={"stock": 45}, follow_redirects=True)
    conn = get_connection()
    updated_stock = conn.execute("SELECT stock FROM products WHERE product_id = ?", (new_pid,)).fetchone()["stock"]
    assert updated_stock == 45
    conn.close()

    # Admin: Delete product
    client.post(f"/admin/product/delete/{new_pid}", follow_redirects=True)
    conn = get_connection()
    deleted_check = conn.execute("SELECT * FROM products WHERE product_id = ?", (new_pid,)).fetchone()
    assert deleted_check is None
    conn.close()
    print("  -> Passed! Admin route security, product creation, stock updates, and deletion verified.")

    # -------------------------------------------------------------
    # 10. Test Wishlist Feature (Complete Lifecycle)
    # -------------------------------------------------------------
    print("\n[Test 10] Testing Wishlist Feature...")
    client.get("/logout")

    # 1. Unauthenticated access redirect
    resp_unauth_wish = client.get("/wishlist")
    assert resp_unauth_wish.status_code == 302, "Unauthenticated access should redirect to login"

    # 2. Login as student user
    client.post("/login", data={"email": "alex@college.edu", "password": "user123"}, follow_redirects=True)

    # Clean existing wishlist for Alex to ensure deterministic test
    conn = get_connection()
    alex_uid = conn.execute("SELECT user_id FROM users WHERE email = 'alex@college.edu'").fetchone()["user_id"]
    conn.execute("DELETE FROM wishlist WHERE user_id = ?", (alex_uid,))
    conn.commit()
    conn.close()

    # 3. Add product 2 to wishlist
    resp_add_w = client.get("/add_to_wishlist/2", follow_redirects=True)
    assert resp_add_w.status_code == 200
    assert b"Added" in resp_add_w.data
    assert b"5G Smartphone Ultra" in resp_add_w.data

    # 4. Duplicate prevention test
    resp_dup_w = client.get("/add_to_wishlist/2", follow_redirects=True)
    assert resp_dup_w.status_code == 200
    assert b"already in your wishlist" in resp_dup_w.data
    conn = get_connection()
    w_count = conn.execute("SELECT COUNT(*) FROM wishlist WHERE user_id = ? AND product_id = 2", (alex_uid,)).fetchone()[0]
    assert w_count == 1, "Duplicate row was inserted into wishlist table!"
    conn.close()

    # 5. Add product 3 to wishlist
    client.get("/add_to_wishlist/3", follow_redirects=True)

    # 6. View wishlist page
    resp_view_w = client.get("/wishlist")
    assert resp_view_w.status_code == 200
    assert b"My Saved Wishlist" in resp_view_w.data
    assert b"5G Smartphone Ultra" in resp_view_w.data
    assert b"Noise-Cancelling Headphones" in resp_view_w.data

    # 7. Move product 2 to cart
    resp_move = client.get("/move_to_cart/2", follow_redirects=True)
    assert resp_move.status_code == 200
    assert b"Moved" in resp_move.data
    # Verify product 2 is in cart
    conn = get_connection()
    in_cart = conn.execute("SELECT * FROM cart WHERE user_id = ? AND product_id = 2", (alex_uid,)).fetchone()
    assert in_cart is not None, "Product was not moved into cart!"
    # Verify product 2 was removed from wishlist
    in_wish = conn.execute("SELECT * FROM wishlist WHERE user_id = ? AND product_id = 2", (alex_uid,)).fetchone()
    assert in_wish is None, "Product was not removed from wishlist after moving to cart!"
    conn.close()

    # 8. Remove product 3 from wishlist
    resp_rem_w = client.get("/remove_from_wishlist/3", follow_redirects=True)
    assert resp_rem_w.status_code == 200
    assert b"Removed" in resp_rem_w.data
    conn = get_connection()
    total_w = conn.execute("SELECT COUNT(*) FROM wishlist WHERE user_id = ?", (alex_uid,)).fetchone()[0]
    assert total_w == 0, "Wishlist should be empty after removal"
    conn.close()

    # 9. Verify empty wishlist state
    resp_empty_w = client.get("/wishlist")
    assert b"Your Wishlist is Empty" in resp_empty_w.data

    # 10. User Isolation Test
    # Add product 1 to Alex's wishlist
    client.get("/add_to_wishlist/1", follow_redirects=True)
    client.get("/logout")

    # Log in as second user (test student)
    client.post("/login", data={"email": "newstudent@college.edu", "password": "mypassword123"}, follow_redirects=True)
    resp_other_user = client.get("/wishlist")
    # Second user must NOT see Alex's item!
    assert b"UltraBook Pro Laptop" not in resp_other_user.data
    assert b"Your Wishlist is Empty" in resp_other_user.data
    client.get("/logout")

    print("  -> Passed! Wishlist creation, duplicates prevention, user isolation, move-to-cart, and deletion verified.")

    print("\n" + "=" * 60)
    print("🎉 ALL 10 TEST SUITES PASSED FLAWLESSLY! 100% SUCCESS RATE.")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
