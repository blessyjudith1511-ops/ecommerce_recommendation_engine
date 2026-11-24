"""
app.py - Main Flask Application for E-Commerce Recommendation Engine
=====================================================================
College Project:
"E-Commerce Recommendation Engine using DBMS and Query Optimization Techniques"

Features:
- Complete User Authentication (Login, Register, Logout, Password Hashing, Session Management)
- Modern Purple Themed UI / UX with Light Lavender Background
- Product Catalog, Search, Category Filter, Price Filter, and Sorting
- Recommendation Engine (Category, Ratings, User Activity Browsing History, Bestsellers)
- Persistent Database Shopping Cart with Stock Validation & Checkout Simulation
- Query Optimization Dashboard (EXPLAIN QUERY PLAN, Indexes, Live Benchmarks, Comparisons)
- Admin Dashboard (Product Catalog Management, Stock Updates, Sales Overview)
"""

from functools import wraps
import re
import time
import uuid
from flask import Flask, render_template, request, session, redirect, url_for, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from database import initialize_database, get_connection
from optimizer import (
    search_products,
    get_all_categories,
    get_optimization_scenarios,
    run_all_benchmarks,
    ensure_benchmark_sample_data
)
from recommendations import (
    get_product_recommendations,
    get_personalized_recommendations,
    get_cart_recommendations,
    log_user_activity
)

app = Flask(__name__)
# Secure session secret key
app.secret_key = "ecommerce-recommendation-engine-college-project-secret-key-2026"

# Ensure database tables, indexes, and initial seed data exist on startup
initialize_database()


# -----------------------------------------------------------------------------
# Context Processor & Decorators
# -----------------------------------------------------------------------------
@app.context_processor
def inject_global_data():
    """
    Injects global variables into all Jinja2 templates:
    - cart_count: Total quantity of items in the user's shopping cart.
    - wishlist_count: Total count of saved items in user's wishlist.
    - user_wishlist_ids: Set of product_ids currently in user's wishlist.
    - current_user: Current logged-in user dictionary (if authenticated).
    - all_categories: List of product categories for navbar and filters.
    """
    user_id = session.get("user_id")
    cart_count = 0
    wishlist_count = 0
    user_wishlist_ids = set()
    current_user = None

    if user_id:
        conn = get_connection()
        # Calculate sum of item quantities in user's cart
        res = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM cart WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if res:
            cart_count = res[0]

        # Calculate count of items in user's wishlist
        w_res = conn.execute(
            "SELECT COUNT(*) FROM wishlist WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if w_res:
            wishlist_count = w_res[0]

        # Fetch product IDs in user's wishlist for fast lookups on cards
        w_ids = conn.execute(
            "SELECT product_id FROM wishlist WHERE user_id = ?",
            (user_id,)
        ).fetchall()
        user_wishlist_ids = {row["product_id"] for row in w_ids}

        # Fetch current user info
        user_row = conn.execute(
            "SELECT user_id, full_name, email, is_admin FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if user_row:
            current_user = dict(user_row)
        conn.close()
    else:
        # Fallback for guest session cart if any
        session_cart = session.get("cart", {})
        cart_count = sum(session_cart.values())

    categories = get_all_categories()
    return {
        "cart_count": cart_count,
        "wishlist_count": wishlist_count,
        "user_wishlist_ids": user_wishlist_ids,
        "current_user": current_user,
        "nav_categories": categories
    }


def login_required(f):
    """Decorator to protect routes requiring authenticated users."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to protect routes restricted to administrators."""
    @wraps(f)

    def decorated_function(*args, **kwargs):
        if "user_id" not in session or session.get("is_admin") != 1:
            flash("Access denied. Administrator privileges required.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated_function


# -----------------------------------------------------------------------------
# Authentication Routes
# -----------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    """Handles new user registration with input validation and password hashing."""
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Form validations
        if not full_name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html", full_name=full_name, email=email)

        # Basic email format check
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            flash("Please enter a valid email address.", "danger")
            return render_template("register.html", full_name=full_name, email=email)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("register.html", full_name=full_name, email=email)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", full_name=full_name, email=email)

        conn = get_connection()
        # Check for existing email (duplicate registration prevention)
        existing_user = conn.execute(
            "SELECT user_id FROM users WHERE email = ?", (email,)
        ).fetchone()

        if existing_user:
            conn.close()
            flash("An account with this email address already exists. Please log in.", "warning")
            return render_template("register.html", full_name=full_name, email=email)

        # Hash password securely
        password_hash = generate_password_hash(password)
        username = email.split("@")[0]

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, full_name, email, password_hash, is_admin)
            VALUES (?, ?, ?, ?, 0)
        """, (username, full_name, email, password_hash))
        conn.commit()
        conn.close()

        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Handles user login, credential verification, and session creation."""
    if "user_id" in session:
        return redirect(url_for("home"))

    next_page = request.args.get("next")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html", email=email)

        conn = get_connection()
        user = conn.execute(
            "SELECT user_id, full_name, email, password_hash, is_admin FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            conn.close()
            flash("Invalid email or password. Please try again.", "danger")
            return render_template("login.html", email=email)

        # Set session variables
        session["user_id"] = user["user_id"]
        session["user_name"] = user["full_name"]
        session["user_email"] = user["email"]
        session["is_admin"] = user["is_admin"]

        # Sync any guest cart items from session into the database cart
        guest_cart = session.get("cart", {})
        if guest_cart:
            for prod_id_str, qty in guest_cart.items():
                try:
                    pid = int(prod_id_str)
                    conn.execute("""
                        INSERT INTO cart (user_id, product_id, quantity)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id, product_id)
                        DO UPDATE SET quantity = quantity + excluded.quantity
                    """, (user["user_id"], pid, qty))
                except Exception:
                    pass
            conn.commit()
            session.pop("cart", None)

        conn.close()
        flash(f"Welcome back, {user['full_name']}!", "success")

        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Clears the session and logs the user out."""
    user_name = session.get("user_name", "User")
    session.clear()
    flash(f"Goodbye {user_name}! You have been logged out successfully.", "info")
    return redirect(url_for("login"))


# -----------------------------------------------------------------------------
# Catalog & Homepage Routes
# -----------------------------------------------------------------------------
@app.route("/")
def home():
    """
    Renders the modern e-commerce homepage with search, category filtering,
    price filtering, sorting, featured products, and personalized recommendations.
    """
    keyword = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    min_price_raw = request.args.get("min_price", "").strip()
    max_price_raw = request.args.get("max_price", "").strip()
    sort_by = request.args.get("sort_by", "rating_desc").strip()

    try:
        min_price = float(min_price_raw) if min_price_raw else None
    except ValueError:
        min_price = None

    try:
        max_price = float(max_price_raw) if max_price_raw else None
    except ValueError:
        max_price = None

    # Fetch filtered products using the optimized search function
    products = search_products(keyword, category, min_price, max_price, sort_by)
    categories = get_all_categories()

    # Personalized recommendations based on logged-in user activity or bestsellers
    user_id = session.get("user_id")
    recommendations = get_personalized_recommendations(user_id=user_id, limit=4)

    # Featured products: top 4 highest rated products store-wide
    conn = get_connection()
    featured_products = conn.execute("""
        SELECT product_id, name, category, price, rating, stock, description, image
        FROM products
        WHERE stock > 0
        ORDER BY rating DESC, price DESC
        LIMIT 4
    """).fetchall()
    conn.close()

    return render_template(
        "index.html",
        products=products,
        categories=categories,
        featured_products=featured_products,
        recommendations=recommendations,
        keyword=keyword,
        selected_category=category,
        min_price=min_price_raw,
        max_price=max_price_raw,
        sort_by=sort_by
    )


@app.route("/product/<int:product_id>")
def product_details(product_id):
    """
    Displays full details for a product, logs user viewing activity,
    and displays dynamic category-based & rating-based recommendations.
    """
    conn = get_connection()
    product = conn.execute(
        "SELECT * FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    conn.close()

    if product is None:
        flash("Product not found.", "danger")
        return redirect(url_for("home"))

    # Log browsing activity for the recommendation engine
    user_id = session.get("user_id")
    log_user_activity(user_id, product_id, activity_type="view")

    # Fetch dynamic SQL recommendations with reasons
    recommendations = get_product_recommendations(product_id, user_id=user_id, limit=4)

    return render_template(
        "product.html",
        product=product,
        recommendations=recommendations
    )


# -----------------------------------------------------------------------------
# Wishlist Routes
# -----------------------------------------------------------------------------
@app.route("/wishlist")
@login_required
def view_wishlist():
    """
    Displays the logged-in user's saved wishlist items from the database.
    """
    user_id = session["user_id"]
    conn = get_connection()
    wishlist_rows = conn.execute("""
        SELECT w.wishlist_id, w.added_at, p.product_id, p.name, p.category,
               p.price, p.rating, p.stock, p.description, p.image
        FROM wishlist w
        JOIN products p ON w.product_id = p.product_id
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
    """, (user_id,)).fetchall()
    conn.close()

    items = [dict(row) for row in wishlist_rows]
    return render_template("wishlist.html", wishlist_items=items)


@app.route("/add_to_wishlist/<int:product_id>", methods=["GET", "POST"])
def add_to_wishlist(product_id):
    """
    Adds a product to the user's wishlist.
    - Requires authenticated user.
    - Prevents duplicate entries.
    - Logs user activity ('wishlist_add') for recommendation engine.
    """
    if "user_id" not in session:
        flash("Please log in to save items to your wishlist.", "info")
        return redirect(url_for("login", next=request.referrer or url_for("home")))

    user_id = session["user_id"]
    conn = get_connection()
    product = conn.execute(
        "SELECT product_id, name FROM products WHERE product_id = ?",
        (product_id,)
    ).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "danger")
        return redirect(request.referrer or url_for("home"))

    # Check for existing wishlist entry to prevent duplicate insertion
    existing = conn.execute(
        "SELECT wishlist_id FROM wishlist WHERE user_id = ? AND product_id = ?",
        (user_id, product_id)
    ).fetchone()

    if existing:
        conn.close()
        flash(f"'{product['name']}' is already in your wishlist.", "info")
        return redirect(request.referrer or url_for("view_wishlist"))

    # Insert into wishlist table
    conn.execute(
        "INSERT INTO wishlist (user_id, product_id) VALUES (?, ?)",
        (user_id, product_id)
    )
    conn.commit()
    conn.close()

    # Log activity for recommendation algorithms
    log_user_activity(user_id, product_id, activity_type="wishlist_add")
    flash(f"❤️ Added '{product['name']}' to your wishlist!", "success")
    return redirect(request.referrer or url_for("view_wishlist"))


@app.route("/remove_from_wishlist/<int:product_id>", methods=["GET", "POST"])
@login_required
def remove_from_wishlist(product_id):
    """Removes a product from the user's wishlist."""
    user_id = session["user_id"]
    conn = get_connection()
    product = conn.execute(
        "SELECT name FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()

    conn.execute(
        "DELETE FROM wishlist WHERE user_id = ? AND product_id = ?",
        (user_id, product_id)
    )
    conn.commit()
    conn.close()

    prod_name = product["name"] if product else "Product"
    flash(f"Removed '{prod_name}' from your wishlist.", "info")
    return redirect(request.referrer or url_for("view_wishlist"))


@app.route("/move_to_cart/<int:product_id>", methods=["GET", "POST"])
@login_required
def move_to_cart(product_id):
    """
    Moves an item from the wishlist directly into the shopping cart.
    1. Verifies product stock availability.
    2. Adds product to user's cart in database.
    3. Removes product from wishlist.
    """
    user_id = session["user_id"]
    conn = get_connection()
    product = conn.execute(
        "SELECT product_id, name, stock, price FROM products WHERE product_id = ?",
        (product_id,)
    ).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "danger")
        return redirect(url_for("view_wishlist"))

    if product["stock"] <= 0:
        conn.close()
        flash(f"Sorry, '{product['name']}' is currently out of stock and cannot be moved to cart.", "warning")
        return redirect(url_for("view_wishlist"))

    # Upsert into cart table
    conn.execute("""
        INSERT INTO cart (user_id, product_id, quantity)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, product_id)
        DO UPDATE SET quantity = MIN(quantity + 1, ?)
    """, (user_id, product_id, product["stock"]))

    # Delete from wishlist
    conn.execute(
        "DELETE FROM wishlist WHERE user_id = ? AND product_id = ?",
        (user_id, product_id)
    )
    conn.commit()
    conn.close()

    log_user_activity(user_id, product_id, activity_type="cart_add")
    flash(f"🛒 Moved '{product['name']}' to your shopping cart!", "success")
    return redirect(url_for("view_cart"))


# -----------------------------------------------------------------------------
# Shopping Cart & Checkout Routes
# -----------------------------------------------------------------------------
@app.route("/cart")
@login_required
def view_cart():
    """
    Displays the logged-in user's shopping cart items from the database.
    Calculates subtotal, total, and displays cart recommendations.
    """
    user_id = session["user_id"]
    conn = get_connection()

    cart_rows = conn.execute("""
        SELECT c.cart_id, c.quantity, p.product_id, p.name, p.category, p.price,
               p.stock, p.image, (c.quantity * p.price) AS subtotal
        FROM cart c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
        ORDER BY c.added_at DESC
    """, (user_id,)).fetchall()

    cart_items = [dict(row) for row in cart_rows]
    total_amount = sum(item["subtotal"] for item in cart_items)
    cart_product_ids = [item["product_id"] for item in cart_items]
    conn.close()

    # Recommendations complementary to what's in the cart
    cart_recommendations = get_cart_recommendations(user_id, cart_product_ids, limit=3)

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total=total_amount,
        recommendations=cart_recommendations
    )


@app.route("/add_to_cart/<int:product_id>", methods=["GET", "POST"])
def add_to_cart(product_id):
    """
    Adds a product to the shopping cart with stock validation.
    Supports both logged-in database cart and guest session cart.
    """
    conn = get_connection()
    product = conn.execute(
        "SELECT product_id, name, stock, price FROM products WHERE product_id = ?",
        (product_id,)
    ).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "danger")
        return redirect(url_for("home"))

    if product["stock"] <= 0:
        conn.close()
        flash(f"Sorry, '{product['name']}' is currently out of stock.", "warning")
        return redirect(request.referrer or url_for("home"))

    # Requested quantity
    try:
        qty_requested = int(request.form.get("quantity", 1))
        if qty_requested <= 0:
            qty_requested = 1
    except (ValueError, TypeError):
        qty_requested = 1

    user_id = session.get("user_id")

    if user_id:
        # Check current cart quantity for this user
        existing_cart_item = conn.execute(
            "SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        ).fetchone()

        current_qty = existing_cart_item["quantity"] if existing_cart_item else 0
        new_qty = current_qty + qty_requested

        if new_qty > product["stock"]:
            allowed = product["stock"] - current_qty
            conn.close()
            if allowed <= 0:
                flash(f"Cannot add more '{product['name']}'. Maximum available stock ({product['stock']}) already in cart.", "warning")
            else:
                flash(f"Only {allowed} more units of '{product['name']}' can be added due to stock limits.", "warning")
            return redirect(url_for("view_cart"))

        # Upsert into cart table
        conn.execute("""
            INSERT INTO cart (user_id, product_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, product_id)
            DO UPDATE SET quantity = excluded.quantity
        """, (user_id, product_id, new_qty))
        conn.commit()
        conn.close()

        # Log cart addition activity for recommendation engine
        log_user_activity(user_id, product_id, activity_type="cart_add")
        flash(f"Added {qty_requested} × '{product['name']}' to your cart!", "success")
        return redirect(url_for("view_cart"))

    else:
        # Guest user: redirect to login so cart is properly user-associated
        flash("Please log in to add items to your cart.", "info")
        return redirect(url_for("login", next=url_for("product_details", product_id=product_id)))


@app.route("/update_cart/<int:product_id>", methods=["POST"])
@login_required
def update_cart(product_id):
    """Updates quantity or increases/decreases quantity in the cart with stock constraints."""
    user_id = session["user_id"]
    action = request.form.get("action", "")

    conn = get_connection()
    product = conn.execute(
        "SELECT stock, name FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()

    cart_item = conn.execute(
        "SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?",
        (user_id, product_id)
    ).fetchone()

    if not product or not cart_item:
        conn.close()
        return redirect(url_for("view_cart"))

    current_qty = cart_item["quantity"]
    max_stock = product["stock"]

    if action == "increase":
        if current_qty < max_stock:
            conn.execute(
                "UPDATE cart SET quantity = quantity + 1 WHERE user_id = ? AND product_id = ?",
                (user_id, product_id)
            )
            conn.commit()
        else:
            flash(f"Cannot add more. Available stock for '{product['name']}' is {max_stock}.", "warning")
    elif action == "decrease":
        if current_qty > 1:
            conn.execute(
                "UPDATE cart SET quantity = quantity - 1 WHERE user_id = ? AND product_id = ?",
                (user_id, product_id)
            )
            conn.commit()
        else:
            # If quantity reaches 0, remove item
            conn.execute(
                "DELETE FROM cart WHERE user_id = ? AND product_id = ?",
                (user_id, product_id)
            )
            conn.commit()
            flash(f"Removed '{product['name']}' from cart.", "info")

    conn.close()
    return redirect(url_for("view_cart"))


@app.route("/remove_from_cart/<int:product_id>", methods=["GET", "POST"])
@login_required
def remove_from_cart(product_id):
    """Removes a product completely from the user's cart."""
    user_id = session["user_id"]
    conn = get_connection()
    conn.execute(
        "DELETE FROM cart WHERE user_id = ? AND product_id = ?",
        (user_id, product_id)
    )
    conn.commit()
    conn.close()
    flash("Item removed from your cart.", "info")
    return redirect(url_for("view_cart"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    """
    Handles checkout and demo payment processing:
    GET: Renders checkout payment options (Demo UPI, Demo Card, Cash on Delivery)
         with cart review and demonstration outcome selector.
    POST: Processes simulated payment, generates unique transaction ID,
          updates orders and payments tables with payment_status (Paid, Pending, Failed),
          adjusts stock if successful, and redirects to confirmation or retry.
    """
    user_id = session["user_id"]
    conn = get_connection()
    cursor = conn.cursor()

    # Fetch current cart items
    cart_items = cursor.execute("""
        SELECT c.cart_id, c.quantity, p.product_id, p.name, p.price, p.stock, p.category, p.image
        FROM cart c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
    """, (user_id,)).fetchall()

    if not cart_items:
        conn.close()
        flash("Your cart is empty. Add products before checking out.", "warning")
        return redirect(url_for("view_cart"))

    # Stock verification
    for item in cart_items:
        if item["quantity"] > item["stock"]:
            conn.close()
            flash(f"Cannot checkout: '{item['name']}' only has {item['stock']} in stock.", "danger")
            return redirect(url_for("view_cart"))

    total_amount = sum(item["quantity"] * item["price"] for item in cart_items)

    if request.method == "GET":
        conn.close()
        return render_template(
            "checkout.html",
            cart_items=cart_items,
            total_amount=total_amount
        )

    # POST: Process demo payment
    payment_method = request.form.get("payment_method", "Demo Card").strip()
    simulation_outcome = request.form.get("simulation_outcome", "success").strip()

    # Generate unique transaction ID
    # Format: TXN-AURA-<timestamp>-<6_hex>
    txn_id = f"TXN-AURA-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"

    try:
        if simulation_outcome == "failure" and payment_method != "Cash on Delivery":
            # Simulated Payment Failure (For demonstration & viva testing)
            payment_status = "Failed"
            order_status = "Failed"

            # Create failed order record for audit
            cursor.execute("""
                INSERT INTO orders (user_id, total_amount, status, payment_method, payment_status, transaction_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, total_amount, order_status, payment_method, payment_status, txn_id))
            order_id = cursor.lastrowid

            # Record failed transaction in payments table
            cursor.execute("""
                INSERT INTO payments (order_id, user_id, amount, payment_method, payment_status, transaction_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (order_id, user_id, total_amount, payment_method, payment_status, txn_id))
            conn.commit()
            conn.close()

            flash(f"❌ Demo Payment Declined: The simulated transaction ({txn_id}) was declined. You can retry with another method.", "danger")
            return redirect(url_for("payment_failed", order_id=order_id))

        # Successful / COD Payment
        if payment_method == "Cash on Delivery":
            payment_status = "Pending"
            order_status = "Completed"
        else:
            payment_status = "Paid"
            order_status = "Completed"

        # 1. Create order record
        cursor.execute("""
            INSERT INTO orders (user_id, total_amount, status, payment_method, payment_status, transaction_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, total_amount, order_status, payment_method, payment_status, txn_id))
        order_id = cursor.lastrowid

        # 2. Insert line items & deduct stock
        for item in cart_items:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (?, ?, ?, ?)
            """, (order_id, item["product_id"], item["quantity"], item["price"]))

            cursor.execute("""
                UPDATE products
                SET stock = stock - ?
                WHERE product_id = ?
            """, (item["quantity"], item["product_id"]))

            # Log purchase activity for recommendation engine
            cursor.execute("""
                INSERT INTO user_activity (user_id, product_id, activity_type)
                VALUES (?, ?, 'purchase')
            """, (user_id, item["product_id"]))

        # 3. Record transaction in payments table
        cursor.execute("""
            INSERT INTO payments (order_id, user_id, amount, payment_method, payment_status, transaction_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_id, user_id, total_amount, payment_method, payment_status, txn_id))

        # 4. Clear user's cart
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        if payment_method == "Cash on Delivery":
            flash(f"🎉 Order placed via Cash on Delivery! Payment of ₹{total_amount:,.2f} is pending on delivery.", "success")
        else:
            flash(f"🎉 Payment successful! Transaction ID: {txn_id}", "success")

        return redirect(url_for("order_success", order_id=order_id))

    except Exception as e:
        conn.rollback()
        conn.close()
        flash(f"An error occurred during checkout processing: {e}", "danger")
        return redirect(url_for("view_cart"))


@app.route("/order_success/<int:order_id>")
@login_required
def order_success(order_id):
    """
    Displays payment confirmation screen with order invoice and transaction details.
    """
    user_id = session["user_id"]
    conn = get_connection()

    order = conn.execute("""
        SELECT * FROM orders WHERE order_id = ? AND user_id = ?
    """, (order_id, user_id)).fetchone()

    if not order:
        conn.close()
        flash("Order not found.", "danger")
        return redirect(url_for("home"))

    items = conn.execute("""
        SELECT oi.*, p.name, p.category, p.image
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = ?
    """, (order_id,)).fetchall()

    payment = conn.execute("""
        SELECT * FROM payments WHERE order_id = ? ORDER BY payment_id DESC LIMIT 1
    """, (order_id,)).fetchone()
    conn.close()

    return render_template("checkout_success.html", order=order, items=items, payment=payment)


@app.route("/payment_failed/<int:order_id>")
@login_required
def payment_failed(order_id):
    """Displays simulated payment failure screen with error details and retry options."""
    user_id = session["user_id"]
    conn = get_connection()

    order = conn.execute("""
        SELECT * FROM orders WHERE order_id = ? AND user_id = ?
    """, (order_id, user_id)).fetchone()

    payment = conn.execute("""
        SELECT * FROM payments WHERE order_id = ? ORDER BY payment_id DESC LIMIT 1
    """, (order_id,)).fetchone()
    conn.close()

    if not order:
        flash("Order record not found.", "danger")
        return redirect(url_for("home"))

    return render_template("payment_failed.html", order=order, payment=payment)


@app.route("/payments")
@login_required
def payment_history():
    """Displays the user's complete payment and transaction history."""
    user_id = session["user_id"]
    conn = get_connection()

    payments = conn.execute("""
        SELECT p.*, o.status as order_status
        FROM payments p
        LEFT JOIN orders o ON p.order_id = o.order_id
        WHERE p.user_id = ?
        ORDER BY p.payment_date DESC
    """, (user_id,)).fetchall()
    conn.close()

    return render_template("payments.html", payments=payments)


@app.route("/orders")
@login_required
def order_history():
    """Displays past orders placed by the current user."""
    user_id = session["user_id"]
    conn = get_connection()

    orders = conn.execute("""
        SELECT * FROM orders WHERE user_id = ? ORDER BY order_date DESC
    """, (user_id,)).fetchall()

    orders_with_items = []
    for o in orders:
        items = conn.execute("""
            SELECT oi.*, p.name, p.image
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            WHERE oi.order_id = ?
        """, (o["order_id"],)).fetchall()
        orders_with_items.append({"order": o, "order_items": items})

    conn.close()
    return render_template("orders.html", orders=orders_with_items)


# -----------------------------------------------------------------------------
# Query Optimization Dashboard Routes (Key College Project Requirement)
# -----------------------------------------------------------------------------
@app.route("/optimization", methods=["GET", "POST"])
def optimization():
    """
    Renders the Query Optimization Dashboard with:
    - Side-by-side SQL diff (Unoptimized vs Optimized)
    - SQLite EXPLAIN QUERY PLAN breakdown (SCAN vs SEARCH USING INDEX)
    - Live measured execution times (ms)
    - Index utilization explanations
    - Cost-Based Optimizer (CBO) technical insights
    """
    benchmark_results = run_all_benchmarks()

    conn = get_connection()
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_activities = conn.execute("SELECT COUNT(*) FROM user_activity").fetchone()[0]
    
    # List all indexes currently present in the SQLite database
    indexes = conn.execute("""
        SELECT name, tbl_name, sql FROM sqlite_master
        WHERE type = 'index' AND name NOT LIKE 'sqlite_autoindex%'
        ORDER BY tbl_name, name
    """).fetchall()
    conn.close()

    return render_template(
        "optimization.html",
        benchmarks=benchmark_results,
        total_products=total_products,
        total_users=total_users,
        total_orders=total_orders,
        total_activities=total_activities,
        indexes=indexes
    )


@app.route("/optimization/benchmark_dataset", methods=["POST"])
def benchmark_dataset():
    """Generates synthetic rows (5,000 items) to demonstrate index scaling in viva."""
    new_count = ensure_benchmark_sample_data(num_records=5000)
    flash(f"Benchmark dataset populated! Products table now contains {new_count} records.", "success")
    return redirect(url_for("optimization"))


# -----------------------------------------------------------------------------
# Admin Management Routes
# -----------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    """Admin dashboard showing product inventory, stock status, and system metrics."""
    conn = get_connection()
    products = conn.execute("SELECT * FROM products ORDER BY product_id DESC").fetchall()
    total_products = len(products)
    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM orders").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    low_stock_count = conn.execute("SELECT COUNT(*) FROM products WHERE stock <= 5").fetchone()[0]
    conn.close()

    return render_template(
        "admin.html",
        products=products,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue,
        total_users=total_users,
        low_stock_count=low_stock_count
    )


@app.route("/admin/product/add", methods=["GET", "POST"])
@admin_required
def admin_add_product():
    """Adds a new product to the catalog."""
    categories = ["Electronics", "Books", "Fashion", "Accessories", "Home"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        price_raw = request.form.get("price", "0").strip()
        rating_raw = request.form.get("rating", "4.0").strip()
        stock_raw = request.form.get("stock", "10").strip()
        description = request.form.get("description", "").strip()
        image = request.form.get("image", "🛍️").strip() or "🛍️"

        try:
            price = float(price_raw)
            rating = float(rating_raw)
            stock = int(stock_raw)
        except ValueError:
            flash("Please enter valid numeric values for price, rating, and stock.", "danger")
            return render_template("admin_product_form.html", categories=categories, action="Add")

        if not name or not category or price <= 0:
            flash("Name, category, and a positive price are required.", "danger")
            return render_template("admin_product_form.html", categories=categories, action="Add")

        conn = get_connection()
        conn.execute("""
            INSERT INTO products (name, category, price, rating, stock, description, image)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, category, price, rating, stock, description, image))
        conn.commit()
        conn.close()

        flash(f"Product '{name}' added successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_product_form.html", categories=categories, action="Add", product=None)


@app.route("/admin/product/edit/<int:product_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_product(product_id):
    """Edits an existing product in the catalog."""
    categories = ["Electronics", "Books", "Fashion", "Accessories", "Home"]
    conn = get_connection()
    product = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        price_raw = request.form.get("price", "0").strip()
        rating_raw = request.form.get("rating", "4.0").strip()
        stock_raw = request.form.get("stock", "10").strip()
        description = request.form.get("description", "").strip()
        image = request.form.get("image", "🛍️").strip() or "🛍️"

        try:
            price = float(price_raw)
            rating = float(rating_raw)
            stock = int(stock_raw)
        except ValueError:
            conn.close()
            flash("Please enter valid numeric values for price, rating, and stock.", "danger")
            return render_template("admin_product_form.html", categories=categories, action="Edit", product=product)

        conn.execute("""
            UPDATE products
            SET name = ?, category = ?, price = ?, rating = ?, stock = ?, description = ?, image = ?
            WHERE product_id = ?
        """, (name, category, price, rating, stock, description, image, product_id))
        conn.commit()
        conn.close()

        flash(f"Product '{name}' updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    conn.close()
    return render_template("admin_product_form.html", categories=categories, action="Edit", product=product)


@app.route("/admin/product/delete/<int:product_id>", methods=["POST"])
@admin_required
def admin_delete_product(product_id):
    """Deletes a product from the catalog."""
    conn = get_connection()
    conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
    conn.commit()
    conn.close()
    flash("Product deleted successfully.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/product/stock/<int:product_id>", methods=["POST"])
@admin_required
def admin_update_stock(product_id):
    """Quickly updates stock quantity from admin table."""
    try:
        new_stock = int(request.form.get("stock", 0))
        if new_stock < 0:
            new_stock = 0
    except ValueError:
        new_stock = 0

    conn = get_connection()
    conn.execute("UPDATE products SET stock = ? WHERE product_id = ?", (new_stock, product_id))
    conn.commit()
    conn.close()
    flash("Stock quantity updated.", "success")
    return redirect(url_for("admin_dashboard"))


# -----------------------------------------------------------------------------
# Main Application Entry Point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Runs the local Flask development server
    print("\n" + "=" * 60)
    print(" 🛍️  E-Commerce Recommendation Engine Starting...")
    print(" Access URL: http://127.0.0.1:5000")
    print(" Demo User:  alex@college.edu  / Password: user123")
    print(" Admin User: admin@ecommerce.com / Password: admin123")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000)
