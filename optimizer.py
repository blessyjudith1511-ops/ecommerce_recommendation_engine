"""
optimizer.py - Query Optimization and Search Module
===================================================
This module handles:
1. Optimized parameterized product search and filtering for the e-commerce store.
2. Query execution plan inspection using SQLite's EXPLAIN QUERY PLAN.
3. Realistic performance benchmarking between unoptimized and optimized SQL queries.
4. Detailed technical explanations for college project demonstrations and viva.

DBMS Concepts Demonstrated:
- Index vs Full Table Scan (SCAN vs SEARCH)
- Composite Indexing (category, rating DESC) to eliminate temporary B-Tree sort passes
- SARGable (Search Argument Able) WHERE clauses vs function-wrapped expressions
- Column projection (avoiding SELECT *) to minimize disk I/O and memory overhead
- Parameterized queries to enable SQLite query caching and prevent SQL injection
"""

import time
import sqlite3
from database import get_connection, DB_NAME


def search_products(keyword="", category="", min_price=None, max_price=None, sort_by="rating_desc"):
    """
    Executes an optimized, parameterized search query across the products catalog.
    
    Query Optimization Techniques Applied:
    1. Parameterized Queries (?): Prevents SQL injection and allows SQLite to reuse cached query plans.
    2. Specific Column Projection: Retrieves only necessary columns, reducing memory footprint.
    3. Indexed WHERE Filter: Uses category and price indexes for fast row matching.
    4. SARGable Conditions: Clean comparison operators (>=, <=) without wrapping columns in functions.
    5. Stock Filter: Filters out discontinued or out-of-stock items (stock > 0).
    """
    conn = get_connection()
    
    query = """
        SELECT product_id, name, category, price, rating, stock, description, image
        FROM products
        WHERE stock > 0
    """
    parameters = []

    # Filter by keyword (searches name or description)
    if keyword:
        query += " AND (name LIKE ? OR description LIKE ?)"
        parameters.extend([f"%{keyword}%", f"%{keyword}%"])

    # Filter by category (Indexed by idx_category and idx_product_category_rating)
    if category:
        query += " AND category = ?"
        parameters.append(category)

    # Filter by minimum price (Indexed by idx_price)
    if min_price is not None:
        query += " AND price >= ?"
        parameters.append(min_price)

    # Filter by maximum price (Indexed by idx_price)
    if max_price is not None:
        query += " AND price <= ?"
        parameters.append(max_price)

    # Deterministic sorting (Leverages indexes where possible)
    if sort_by == "price_asc":
        query += " ORDER BY price ASC"
    elif sort_by == "price_desc":
        query += " ORDER BY price DESC"
    elif sort_by == "rating_asc":
        query += " ORDER BY rating ASC"
    else:
        # Default: Highest rating first (Leverages idx_product_category_rating)
        query += " ORDER BY rating DESC"

    products = conn.execute(query, parameters).fetchall()
    conn.close()
    return products


def get_all_categories():
    """
    Returns a distinct, sorted list of all product categories.
    Leverages idx_category index.
    """
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT category FROM products ORDER BY category ASC").fetchall()
    conn.close()
    return [r["category"] for r in rows]


def get_query_plan(query, parameters=()):
    """
    Runs SQLite's EXPLAIN QUERY PLAN command to inspect how SQLite intends to execute a query.
    Returns a list of formatted explanation steps.
    
    SQLite EXPLAIN QUERY PLAN format:
    id | parent | notused | detail
    Example detail: 'SEARCH products USING INDEX idx_category (category=?)'
    """
    conn = get_connection()
    try:
        plan_cursor = conn.execute(f"EXPLAIN QUERY PLAN {query}", parameters)
        rows = plan_cursor.fetchall()
        # Extract the human-readable 'detail' column
        details = [dict(r)["detail"] for r in rows]
        conn.close()
        return details
    except Exception as e:
        conn.close()
        return [f"Execution plan error: {e}"]


def benchmark_query(query, parameters=(), iterations=50):
    """
    Accurately measures real execution time of a SQL query by running it
    multiple times and computing the average execution time in milliseconds.
    
    Returns:
    - avg_time_ms: Average execution time per query in milliseconds.
    - row_count: Number of rows returned.
    """
    conn = get_connection()
    # Warm up cache with 1 run
    cursor = conn.execute(query, parameters)
    sample_rows = cursor.fetchall()
    row_count = len(sample_rows)

    start_time = time.perf_counter()
    for _ in range(iterations):
        c = conn.execute(query, parameters)
        c.fetchall()
    end_time = time.perf_counter()

    conn.close()
    avg_time_ms = ((end_time - start_time) / iterations) * 1000.0
    return round(avg_time_ms, 4), row_count


def get_optimization_scenarios():
    """
    Defines realistic e-commerce query scenarios comparing unoptimized
    queries vs optimized queries, their execution plans, and educational explanations.
    """
    scenarios = [
        {
            "id": "scenario_category_rating",
            "title": "Scenario 1: Category Filter with Rating Sort",
            "concept": "Composite Indexing (category, rating DESC) vs Full Table Scan & Temporary B-Tree Sort",
            "description": "Fetching top-rated products within a given category for product browsing and category landing pages.",
            "unoptimized": {
                "sql": """-- Unoptimized: Wildcard search invalidates index, selects all columns (*), forces temporary B-Tree sort
SELECT *
FROM products
WHERE category LIKE '%Electronics%'
ORDER BY rating DESC;""",
                "query": "SELECT * FROM products WHERE category LIKE '%Electronics%' ORDER BY rating DESC",
                "params": ()
            },
            "optimized": {
                "sql": """-- Optimized: Exact parameterized equality match, specific column projections,
-- leverages composite index 'idx_product_category_rating' to eliminate sorting step, LIMIT 10
SELECT product_id, name, category, price, rating, stock
FROM products
WHERE category = ?
ORDER BY rating DESC
LIMIT 10;""",
                "query": "SELECT product_id, name, category, price, rating, stock FROM products WHERE category = ? ORDER BY rating DESC LIMIT 10",
                "params": ("Electronics",)
            },
            "indexes_used": ["idx_product_category_rating (Composite: category, rating DESC)", "idx_category"],
            "explanation": (
                "1. Wildcard LIKE '%...' cannot use an index B-Tree because the leading character is unknown, forcing a full table scan.\n"
                "2. The composite index on (category, rating DESC) stores the rows already sorted by rating for each category. "
                "This completely eliminates SQLite's costly 'USE TEMP B-TREE FOR ORDER BY' sorting operation.\n"
                "3. SELECT with specific columns avoids loading unnecessary large text blobs into memory.\n"
                "4. LIMIT 10 stops scanning as soon as the first 10 matching rows are found."
            )
        },
        {
            "id": "scenario_price_filtering",
            "title": "Scenario 2: Price Range Filtering",
            "concept": "SARGable Search Arguments vs Non-SARGable Arithmetic Expressions",
            "description": "Filtering products under a budget (e.g. products under ₹2,000) for bargain hunting.",
            "unoptimized": {
                "sql": """-- Unoptimized: Arithmetic expression (price + 0) or CAST on column breaks index usage (Non-SARGable)
SELECT *
FROM products
WHERE (price + 0) <= 2000.0
ORDER BY price ASC;""",
                "query": "SELECT * FROM products WHERE (price + 0) <= 2000.0 ORDER BY price ASC",
                "params": ()
            },
            "optimized": {
                "sql": """-- Optimized: Direct comparison on indexed column 'price', parameterized, LIMIT 10
SELECT product_id, name, category, price, rating
FROM products
WHERE price <= ?
ORDER BY price ASC
LIMIT 10;""",
                "query": "SELECT product_id, name, category, price, rating FROM products WHERE price <= ? ORDER BY price ASC LIMIT 10",
                "params": (2000.0,)
            },
            "indexes_used": ["idx_price (B-Tree on price ASC)"],
            "explanation": (
                "1. In SQL, expressions like 'column + 0' or 'UPPER(column)' are non-SARGable. "
                "The database cannot use the B-Tree index on 'price' because it must evaluate the math expression for every single row.\n"
                "2. Writing clean direct comparisons ('price <= ?') allows SQLite to jump straight to the matching range in the B-Tree index.\n"
                "3. Indexed sorting on 'price ASC' retrieves rows directly in ascending order without in-memory sorting."
            )
        },
        {
            "id": "scenario_recommendation_query",
            "title": "Scenario 3: Recommendation Engine Query",
            "concept": "Subquery Elimination, Parameterization & Index-Assisted Exclusion",
            "description": "Retrieving related products in the same category while excluding the currently viewed product.",
            "unoptimized": {
                "sql": """-- Unoptimized: Correlated subquery executed for category, NOT IN subquery without LIMIT
SELECT *
FROM products
WHERE category = (SELECT category FROM products WHERE product_id = 1)
  AND product_id NOT IN (1)
ORDER BY rating DESC;""",
                "query": "SELECT * FROM products WHERE category = (SELECT category FROM products WHERE product_id = 1) AND product_id NOT IN (1) ORDER BY rating DESC",
                "params": ()
            },
            "optimized": {
                "sql": """-- Optimized: Category is resolved beforehand and passed as a parameter;
-- leverages idx_product_category_rating; stops at LIMIT 4
SELECT product_id, name, category, price, rating, stock, image
FROM products
WHERE category = ?
  AND product_id != ?
  AND stock > 0
ORDER BY rating DESC
LIMIT 4;""",
                "query": "SELECT product_id, name, category, price, rating, stock, image FROM products WHERE category = ? AND product_id != ? AND stock > 0 ORDER BY rating DESC LIMIT 4",
                "params": ("Electronics", 1)
            },
            "indexes_used": ["idx_product_category_rating", "sqlite_autoindex_products_1 (Primary Key on product_id)"],
            "explanation": (
                "1. The unoptimized query forces SQLite to execute an inner subquery to discover the category on every evaluation.\n"
                "2. In the optimized query, the application fetches the category once and supplies it via a parameterized query.\n"
                "3. The primary key index on product_id quickly handles the exclusion ('product_id != ?').\n"
                "4. LIMIT 4 prevents the engine from sorting and loading the entire category."
            )
        },
        {
            "id": "scenario_user_activity_join",
            "title": "Scenario 4: User Interaction Aggregation (JOIN vs Subquery)",
            "concept": "Indexed JOIN with Foreign Keys vs Correlated Scalar Subqueries (N+1 Problem)",
            "description": "Finding the most viewed products across the store for the 'Trending Items' recommendation card.",
            "unoptimized": {
                "sql": """-- Unoptimized: Correlated scalar subquery executed for every single product (O(N) queries)
SELECT p.product_id, p.name, p.category,
       (SELECT COUNT(*) FROM user_activity WHERE product_id = p.product_id) AS total_views
FROM products p
ORDER BY total_views DESC;""",
                "query": "SELECT p.product_id, p.name, p.category, (SELECT COUNT(*) FROM user_activity WHERE product_id = p.product_id) AS total_views FROM products p ORDER BY total_views DESC",
                "params": ()
            },
            "optimized": {
                "sql": """-- Optimized: Single grouped LEFT JOIN utilizing foreign key index 'idx_activity_prod', LIMIT 5
SELECT p.product_id, p.name, p.category, p.price,
       COUNT(ua.activity_id) AS total_views
FROM products p
LEFT JOIN user_activity ua ON p.product_id = ua.product_id
GROUP BY p.product_id
ORDER BY total_views DESC
LIMIT 5;""",
                "query": "SELECT p.product_id, p.name, p.category, p.price, COUNT(ua.activity_id) AS total_views FROM products p LEFT JOIN user_activity ua ON p.product_id = ua.product_id GROUP BY p.product_id ORDER BY total_views DESC LIMIT 5",
                "params": ()
            },
            "indexes_used": ["idx_activity_prod (B-Tree on user_activity.product_id)", "PRIMARY KEY on products.product_id"],
            "explanation": (
                "1. The unoptimized query suffers from the classic N+1 problem: for every row in 'products', SQLite runs a separate sub-query scanning 'user_activity'.\n"
                "2. The optimized query executes a single indexed hash/merge join.\n"
                "3. The index 'idx_activity_prod' allows instant grouping of activities by product_id without scanning unrelated records."
            )
        }
    ]
    return scenarios


def run_all_benchmarks():
    """
    Executes live benchmarks on all optimization scenarios and captures:
    - EXPLAIN QUERY PLAN output for both queries
    - Actual measured execution time in milliseconds
    - Returned row counts
    """
    scenarios = get_optimization_scenarios()
    results = []

    for s in scenarios:
        unopt = s["unoptimized"]
        opt = s["optimized"]

        # Run EXPLAIN QUERY PLAN
        unopt_plan = get_query_plan(unopt["query"], unopt["params"])
        opt_plan = get_query_plan(opt["query"], opt["params"])

        # Measure actual timings (run 30 iterations for reliable precision)
        unopt_time, unopt_rows = benchmark_query(unopt["query"], unopt["params"], iterations=30)
        opt_time, opt_rows = benchmark_query(opt["query"], opt["params"], iterations=30)

        # Calculate speedup percentage
        speedup = 1.0
        if opt_time > 0:
            speedup = round(unopt_time / opt_time, 2)

        results.append({
            "id": s["id"],
            "title": s["title"],
            "concept": s["concept"],
            "description": s["description"],
            "unoptimized_sql": unopt["sql"],
            "unoptimized_plan": unopt_plan,
            "unoptimized_time": unopt_time,
            "unoptimized_rows": unopt_rows,
            "optimized_sql": opt["sql"],
            "optimized_plan": opt_plan,
            "optimized_time": opt_time,
            "optimized_rows": opt_rows,
            "speedup": speedup,
            "indexes_used": s["indexes_used"],
            "explanation": s["explanation"]
        })

    return results


def ensure_benchmark_sample_data(num_records=5000):
    """
    Optional College Viva Helper:
    Populates a temporary table or adds synthetic rows to demonstrate how the
    SQLite Cost-Based Optimizer switches from SCAN to SEARCH when table size grows!
    """
    conn = get_connection()
    current_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    
    # If table is already large, return current count
    if current_count >= num_records:
        conn.close()
        return current_count

    categories = ["Electronics", "Books", "Fashion", "Accessories", "Home"]
    items = []
    for i in range(current_count + 1, num_records + 1):
        cat = categories[i % len(categories)]
        items.append((
            f"Demo Item {i}",
            cat,
            round(100.0 + (i % 5000), 2),
            round(3.0 + ((i % 20) / 10.0), 1),
            20 + (i % 100),
            f"Synthetic benchmark item #{i} generated for query optimization testing.",
            "📦"
        ))
    
    conn.executemany("""
        INSERT INTO products (name, category, price, rating, stock, description, image)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, items)
    conn.commit()
    new_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()
    return new_count
