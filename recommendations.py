"""
recommendations.py - SQL & Python Recommendation Engine
========================================================
This module implements the recommendation system for the E-Commerce platform.
All recommendations are computed dynamically using optimized SQL queries.

Recommendation Strategies:
1. Category-Based & Rating-Weighted:
   Recommends top-rated products from the same category when viewing a product.
   Reason: "Recommended because you are viewing {category}" / "Highest rated in {category}"

2. User Browsing Activity History:
   Analyzes the user's recent views from `user_activity` table to surface products
   matching the user's demonstrated interests.
   Reason: "Recommended because you browsed {category}"

3. Bestsellers & Popular Items (Collaborative / Sales Activity):
   Aggregates order frequency from `order_items` to recommend crowd favorites.
   Reason: "Trending customer bestseller"

4. Cross-Sell / Cart Additions:
   Recommends top-rated companion items excluding products already in the cart.
   Reason: "Popular additions to your cart"
"""

from database import get_connection


def log_user_activity(user_id, product_id, activity_type="view"):
    """
    Logs an interaction (view, cart_add, purchase) in the user_activity table.
    Enables personalized recommendation queries without blocking page response.
    """
    if not product_id:
        return
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO user_activity (user_id, product_id, activity_type)
            VALUES (?, ?, ?)
        """, (user_id, product_id, activity_type))
        conn.commit()
        conn.close()
    except Exception as e:
        # Failsafe logging so user browsing is never interrupted
        print(f"[Activity Log Error]: {e}")


def get_product_recommendations(product_id, user_id=None, limit=4):
    """
    Returns recommendations tailored for a specific product detail page.
    - Primary Strategy: Same category, sorted by rating descending.
    - Fallback Strategy: Storewide top-rated products if category has few items.
    """
    conn = get_connection()
    recommendations = []

    # Step 1: Fetch the target product's category
    target_product = conn.execute(
        "SELECT category, name FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()

    if not target_product:
        conn.close()
        return []

    category = target_product["category"]

    # Step 2: Query top-rated products in the same category (indexed by idx_product_category_rating)
    # Exclude the current product to avoid recommending what is already open
    same_category_query = """
        SELECT product_id, name, category, price, rating, stock, description, image
        FROM products
        WHERE category = ?
          AND product_id != ?
          AND stock > 0
        ORDER BY rating DESC
        LIMIT ?
    """
    cat_rows = conn.execute(same_category_query, (category, product_id, limit)).fetchall()

    for row in cat_rows:
        item = dict(row)
        item["recommendation_reason"] = f"Top rated in {category}"
        item["badge_color"] = "purple"
        recommendations.append(item)

    # Step 3: If fewer than limit items found, supplement with storewide top-rated items
    if len(recommendations) < limit:
        needed = limit - len(recommendations)
        existing_ids = [product_id] + [r["product_id"] for r in recommendations]
        placeholders = ",".join("?" for _ in existing_ids)
        
        fallback_query = f"""
            SELECT product_id, name, category, price, rating, stock, description, image
            FROM products
            WHERE product_id NOT IN ({placeholders})
              AND stock > 0
            ORDER BY rating DESC
            LIMIT ?
        """
        params = existing_ids + [needed]
        fallback_rows = conn.execute(fallback_query, params).fetchall()

        for row in fallback_rows:
            item = dict(row)
            item["recommendation_reason"] = "Customer top-rated favorite"
            item["badge_color"] = "gold"
            recommendations.append(item)

    conn.close()
    return recommendations


def get_personalized_recommendations(user_id=None, limit=4):
    """
    Provides personalized recommendations for the homepage.
    - If user is logged in with viewing history: surfaces top items in their most viewed category.
    - If guest or new user: surfaces overall bestselling and top-rated products.
    """
    conn = get_connection()
    recommendations = []
    preferred_category = None

    # Step 1: Check if user has recent activity
    if user_id:
        activity_query = """
            SELECT p.category, COUNT(*) as interaction_count
            FROM user_activity ua
            JOIN products p ON ua.product_id = p.product_id
            WHERE ua.user_id = ?
            GROUP BY p.category
            ORDER BY interaction_count DESC, MAX(ua.timestamp) DESC
            LIMIT 1
        """
        top_pref = conn.execute(activity_query, (user_id,)).fetchone()
        if top_pref:
            preferred_category = top_pref["category"]

    # Step 2: If preferred category exists, query top products from that category
    if preferred_category:
        cat_query = """
            SELECT product_id, name, category, price, rating, stock, description, image
            FROM products
            WHERE category = ?
              AND stock > 0
            ORDER BY rating DESC
            LIMIT ?
        """
        rows = conn.execute(cat_query, (preferred_category, limit)).fetchall()
        for row in rows:
            item = dict(row)
            item["recommendation_reason"] = f"Recommended because you browsed {preferred_category}"
            item["badge_color"] = "purple"
            recommendations.append(item)

    # Step 3: If still under limit (or guest user), populate with Bestsellers & Top Rated
    if len(recommendations) < limit:
        needed = limit - len(recommendations)
        existing_ids = [r["product_id"] for r in recommendations]
        
        if existing_ids:
            placeholders = ",".join("?" for _ in existing_ids)
            bestseller_query = f"""
                SELECT p.product_id, p.name, p.category, p.price, p.rating, p.stock, p.description, p.image,
                       COALESCE(SUM(oi.quantity), 0) AS total_sold
                FROM products p
                LEFT JOIN order_items oi ON p.product_id = oi.product_id
                WHERE p.stock > 0
                  AND p.product_id NOT IN ({placeholders})
                GROUP BY p.product_id
                ORDER BY total_sold DESC, p.rating DESC
                LIMIT ?
            """
            params = existing_ids + [needed]
        else:
            bestseller_query = """
                SELECT p.product_id, p.name, p.category, p.price, p.rating, p.stock, p.description, p.image,
                       COALESCE(SUM(oi.quantity), 0) AS total_sold
                FROM products p
                LEFT JOIN order_items oi ON p.product_id = oi.product_id
                WHERE p.stock > 0
                GROUP BY p.product_id
                ORDER BY total_sold DESC, p.rating DESC
                LIMIT ?
            """
            params = [needed]

        bestsellers = conn.execute(bestseller_query, params).fetchall()
        for row in bestsellers:
            item = dict(row)
            if item.get("total_sold", 0) > 0:
                item["recommendation_reason"] = "🔥 Trending Bestseller"
                item["badge_color"] = "orange"
            else:
                item["recommendation_reason"] = "⭐ Highest Rated Choice"
                item["badge_color"] = "gold"
            recommendations.append(item)

    conn.close()
    return recommendations


def get_cart_recommendations(user_id=None, cart_product_ids=None, limit=3):
    """
    Returns recommendations for the cart page to encourage cross-selling.
    Excludes items already present in the cart.
    """
    if cart_product_ids is None:
        cart_product_ids = []

    conn = get_connection()
    recommendations = []

    if cart_product_ids:
        placeholders = ",".join("?" for _ in cart_product_ids)
        query = f"""
            SELECT product_id, name, category, price, rating, stock, description, image
            FROM products
            WHERE product_id NOT IN ({placeholders})
              AND stock > 0
            ORDER BY rating DESC
            LIMIT ?
        """
        params = list(cart_product_ids) + [limit]
    else:
        query = """
            SELECT product_id, name, category, price, rating, stock, description, image
            FROM products
            WHERE stock > 0
            ORDER BY rating DESC
            LIMIT ?
        """
        params = [limit]

    rows = conn.execute(query, params).fetchall()
    for row in rows:
        item = dict(row)
        item["recommendation_reason"] = "✨ Popular addition to complete your order"
        item["badge_color"] = "lavender"
        recommendations.append(item)

    conn.close()
    return recommendations
