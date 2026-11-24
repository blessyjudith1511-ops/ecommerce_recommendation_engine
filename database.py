"""
database.py - Database Connection and Initialization Module
=============================================================
This file manages the SQLite database connection, table creation,
indexing, and initial seed data for the E-Commerce Recommendation Engine.

College Project Highlights:
- Foreign Key enforcement enabled with PRAGMA foreign_keys = ON
- Normalized Relational Schema (Users, Products, Cart, Orders, Order_Items, User_Activity)
- Single-column and Composite Indexes for Query Optimization
- Secure password hashing using Werkzeug (no plain text passwords)
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_NAME = "ecommerce.db"


def get_connection():
    """
    Creates and returns a connection to the SQLite database.
    - row_factory is set to sqlite3.Row so columns can be accessed by name (e.g. row['name']).
    - Enables foreign key constraint enforcement in SQLite.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    # SQLite requires PRAGMA foreign_keys = ON on every new connection
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def initialize_database():
    """
    Initializes all database tables, creates performance indexes,
    and populates sample data if the tables are empty.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ---------------------------------------------------------
    # 1. TABLE: products
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL CHECK(price >= 0),
            rating REAL DEFAULT 0 CHECK(rating >= 0 AND rating <= 5),
            stock INTEGER DEFAULT 0 CHECK(stock >= 0),
            description TEXT,
            image TEXT
        )
    """)

    # ---------------------------------------------------------
    # 2. TABLE: users
    # Note: Passwords are encrypted using Werkzeug generate_password_hash
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------------------------------------------------
    # 3. TABLE: cart (User-specific shopping cart)
    # UNIQUE(user_id, product_id) prevents duplicate product rows per user
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            cart_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
            UNIQUE(user_id, product_id)
        )
    """)

    # ---------------------------------------------------------
    # 4. TABLE: orders (Order history header)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_amount REAL NOT NULL CHECK(total_amount >= 0),
            status TEXT DEFAULT 'Completed',
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # Check if orders table needs migration or payment columns
    order_columns = [col[1] for col in cursor.execute("PRAGMA table_info(orders)").fetchall()]
    order_count = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if order_count == 0 and "total_amount" not in order_columns:
        cursor.execute("DROP TABLE orders;")
        cursor.execute("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total_amount REAL NOT NULL CHECK(total_amount >= 0),
                status TEXT DEFAULT 'Completed',
                payment_method TEXT DEFAULT 'Demo Card',
                payment_status TEXT DEFAULT 'Paid',
                transaction_id TEXT DEFAULT '',
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
    else:
        if "payment_method" not in order_columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'Demo Card';")
        if "payment_status" not in order_columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'Paid';")
        if "transaction_id" not in order_columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN transaction_id TEXT DEFAULT '';")

    # ---------------------------------------------------------
    # 5. TABLE: order_items (Normalized order line items)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL CHECK(unit_price >= 0),
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
        )
    """)

    # ---------------------------------------------------------
    # 6. TABLE: payments (Normalized Payment & Transaction History)
    # Stores simulated transactions with unique transaction IDs and status
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            payment_method TEXT NOT NULL, -- 'Demo UPI', 'Demo Card', 'Cash on Delivery'
            payment_status TEXT NOT NULL, -- 'Paid', 'Pending', 'Failed'
            transaction_id TEXT UNIQUE NOT NULL,
            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE SET NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # ---------------------------------------------------------
    # 7. TABLE: user_activity (Browsing & Interaction Tracking)
    # Records product views and cart additions to power recommendation engine
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activity (
            activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER NOT NULL,
            activity_type TEXT NOT NULL, -- 'view', 'cart_add', 'purchase', 'wishlist_add'
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
            FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
        )
    """)

    # ---------------------------------------------------------
    # 7. TABLE: wishlist (User-isolated saved products)
    # UNIQUE(user_id, product_id) strictly prevents duplicate wishlist entries
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wishlist (
            wishlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
            UNIQUE(user_id, product_id)
        )
    """)

    # ---------------------------------------------------------
    # 8. INDEXES (Core Query Optimization Concept)
    # ---------------------------------------------------------
    # Single-column indexes:
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON products(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price ON products(price);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating ON products(rating);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cart_user ON cart(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_txn ON payments(transaction_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_user ON wishlist(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user ON user_activity(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_prod ON user_activity(product_id);")

    # Composite indexes (multi-column) for common filtered + sorted queries:
    # Optimizes: WHERE category = ? ORDER BY rating DESC
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_category_rating
        ON products(category, rating DESC);
    """)

    # Optimizes: WHERE category = ? AND price <= ?
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_product_category_price
        ON products(category, price ASC);
    """)

    # Optimizes: WHERE user_id = ? AND activity_type = ?
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_composite
        ON user_activity(user_id, activity_type, product_id);
    """)

    # ---------------------------------------------------------
    # 8. MIGRATION CHECK FOR EXISTING USERS TABLE
    # If users table already existed from old code without password_hash, migrate it safely
    # ---------------------------------------------------------
    # Check if existing users table needs schema modernization
    user_columns = [col[1] for col in cursor.execute("PRAGMA table_info(users)").fetchall()]
    user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0 and "username" in user_columns:
        # Safely drop empty old users table and recreate clean modern schema
        cursor.execute("DROP TABLE users;")
        cursor.execute("""
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        if "password_hash" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT '';")
        if "full_name" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT 'User';")
        if "is_admin" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0;")
        if "created_at" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")

    # ---------------------------------------------------------
    # 9. SEED DATA POPULATION
    # ---------------------------------------------------------
    # Seed Products if less than 20 products exist or if product images are missing
    product_count = cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    has_empty_images = cursor.execute("SELECT COUNT(*) FROM products WHERE image = '' OR image IS NULL").fetchone()[0]
    if product_count < 20 or has_empty_images > 0:
        sample_products = [
            # Electronics
            ("UltraBook Pro Laptop", "Electronics", 65000.0, 4.8, 15, "High-performance laptop with 16GB RAM, 512GB SSD and Intel Core i7.", "💻"),
            ("5G Smartphone Ultra", "Electronics", 24999.0, 4.6, 25, "Crisp 120Hz AMOLED display, 64MP AI triple camera, and 5000mAh battery.", "📱"),
            ("Noise-Cancelling Headphones", "Electronics", 2499.0, 4.4, 40, "Over-ear wireless headphones with active noise cancellation and 30-hour battery life.", "🎧"),
            ("RGB Mechanical Keyboard", "Electronics", 1899.0, 4.3, 30, "Tactile blue switches, anti-ghosting keys, and vibrant customizable RGB backlighting.", "⌨️"),
            ("Wireless Ergonomic Mouse", "Electronics", 799.0, 4.5, 50, "Contoured grip, silent clicks, and high-precision 2400 DPI optical sensor.", "🖱️"),
            
            # Books
            ("Python Programming Mastery", "Books", 650.0, 4.9, 35, "Comprehensive guide to Python: from basics to algorithms, web apps, and data science.", "🐍"),
            ("Database Management Systems", "Books", 550.0, 4.8, 40, "College textbook covering relational algebra, SQL, normalization, and query optimization.", "📚"),
            ("Data Structures & Algorithms", "Books", 720.0, 4.7, 20, "In-depth guide with practical implementations, Big-O analysis, and interview problems.", "📖"),
            ("Clean Code Architecture", "Books", 850.0, 4.6, 18, "Professional handbook of software craftsmanship, design patterns, and clean code principles.", "📑"),

            # Fashion
            ("Premium Cotton T-Shirt", "Fashion", 699.0, 4.2, 60, "Breathable 100% bio-washed cotton casual t-shirt for daily comfort.", "👕"),
            ("Slim Fit Denim Jeans", "Fashion", 1499.0, 4.3, 35, "Durable stretchable denim jeans with modern slim fit and classic 5-pocket styling.", "👖"),
            ("Urban Runner Sneakers", "Fashion", 2299.0, 4.5, 20, "Lightweight cushioned athletic running shoes with breathable mesh and shock absorption.", "👟"),
            ("Classic Bomber Jacket", "Fashion", 2899.0, 4.4, 15, "Water-resistant windbreaker bomber jacket with ribbed collar and zip closure.", "🧥"),

            # Accessories
            ("Smart Fitness Watch", "Accessories", 2999.0, 4.7, 25, "Full-touch AMOLED display, heart rate monitor, sleep tracking, and 7-day battery life.", "⌚"),
            ("Anti-Theft Laptop Backpack", "Accessories", 1299.0, 4.4, 30, "Water-resistant 15.6-inch laptop bag with USB charging port and hidden pockets.", "🎒"),
            ("Polarized Aviator Sunglasses", "Accessories", 899.0, 4.2, 45, "Classic metal frame with UV400 polarized scratch-resistant lenses.", "🕶️"),
            ("Genuine Leather Wallet", "Accessories", 699.0, 4.3, 40, "Handcrafted RFID-blocking bifold leather wallet with multiple card slots.", "👛"),

            # Home
            ("Ergonomic Mesh Desk Chair", "Home", 4499.0, 4.5, 12, "Breathable mesh backrest, adjustable height, lumbar support, and 360-degree swivel.", "🪑"),
            ("Smart Dimmable LED Desk Lamp", "Home", 899.0, 4.6, 25, "Touch control LED study lamp with 3 color temperatures and USB charging port.", "💡"),
            ("Insulated Stainless Water Bottle", "Home", 499.0, 4.3, 50, "Double-wall vacuum insulated 1000ml bottle keeping drinks cold for 24 hours.", "🍶")
        ]
        
        # Clear old minimal sample rows if present to ensure clean dataset
        cursor.execute("DELETE FROM products;")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='products';")
        cursor.executemany("""
            INSERT INTO products (name, category, price, rating, stock, description, image)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_products)

    # Seed Users if not present
    user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        # Default Admin User
        admin_pass = generate_password_hash("admin123")
        cursor.execute("""
            INSERT INTO users (username, full_name, email, password_hash, is_admin)
            VALUES (?, ?, ?, ?, ?)
        """, ("admin", "Admin Manager", "admin@ecommerce.com", admin_pass, 1))

        # Default Regular Student User
        student_pass = generate_password_hash("user123")
        cursor.execute("""
            INSERT INTO users (username, full_name, email, password_hash, is_admin)
            VALUES (?, ?, ?, ?, ?)
        """, ("alex", "Alex Student", "alex@college.edu", student_pass, 0))

        conn.commit()

        # Seed sample browsing activity and orders for demonstration
        student_user = cursor.execute("SELECT user_id FROM users WHERE email = 'alex@college.edu'").fetchone()
        if student_user:
            uid = student_user["user_id"]
            # Seed views
            cursor.execute("INSERT INTO user_activity (user_id, product_id, activity_type) VALUES (?, 1, 'view')", (uid,))
            cursor.execute("INSERT INTO user_activity (user_id, product_id, activity_type) VALUES (?, 6, 'view')", (uid,))
            cursor.execute("INSERT INTO user_activity (user_id, product_id, activity_type) VALUES (?, 7, 'view')", (uid,))
            
            # Seed a sample completed order
            cursor.execute("""
                INSERT INTO orders (user_id, total_amount, status)
                VALUES (?, 1200.0, 'Completed')
            """, (uid,))
            order_id = cursor.lastrowid
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (?, 6, 1, 650.0)
            """, (order_id,))
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (?, 7, 1, 550.0)
            """, (order_id,))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully with schema, indexes, and seed data!")
