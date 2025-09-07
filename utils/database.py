import sqlite3


def init_database():
    """Initialize the database with the users table"""
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            coins INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_checkins (
            user_id INTEGER PRIMARY KEY,
            last_checkin_date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    conn.commit()
    conn.close()


def get_user_coins(user_id):
    """Get the coin balance for a specific user"""
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    cursor.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0


def add_coins(user_id, username, amount):
    """Add coins to a user's balance"""
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, coins)
        VALUES (?, ?, COALESCE((SELECT coins FROM users WHERE user_id = ?), 0) + ?)
    ''', (user_id, username, user_id, amount))
    conn.commit()
    conn.close()


def remove_coins(user_id, username, amount):
    """Remove coins from a user's balance (minimum 0)"""
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, coins)
        VALUES (?, ?, MAX(COALESCE((SELECT coins FROM users WHERE user_id = ?), 0) - ?, 0))
    ''', (user_id, username, user_id, amount))
    conn.commit()
    conn.close()


def spend_coins(user_id, username, amount):
    """Spend coins from a user's balance. Returns True if successful, False if insufficient funds"""
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    
    # Check current balance
    current_coins = get_user_coins(user_id)
    if current_coins < amount:
        conn.close()
        return False
    
    # Deduct coins
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, coins)
        VALUES (?, ?, ?)
    ''', (user_id, username, current_coins - amount))
    
    conn.commit()
    conn.close()
    return True


def get_leaderboard(limit=10):
    """Get the top users by coin balance"""
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, coins FROM users ORDER BY coins DESC LIMIT ?', (limit,))
    results = cursor.fetchall()
    conn.close()
    return results


def can_daily_checkin(user_id):
    """Check if a user can perform a daily check-in (based on UTC date)"""
    from datetime import datetime, timezone
    
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    
    # Get the last check-in date
    cursor.execute('SELECT last_checkin_date FROM daily_checkins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if not result:
        return True  # User has never checked in
    
    last_checkin = result[0]
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    return last_checkin != today_utc


def perform_daily_checkin(user_id, username):
    """Perform a daily check-in for a user and return the new coin balance"""
    from datetime import datetime, timezone
    
    conn = sqlite3.connect('shooting_star.db')
    cursor = conn.cursor()
    
    # Add coins
    add_coins(user_id, username, 200)
    
    # Update check-in date
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    cursor.execute('''
        INSERT OR REPLACE INTO daily_checkins (user_id, last_checkin_date)
        VALUES (?, ?)
    ''', (user_id, today_utc))
    
    conn.commit()
    conn.close()
    
    # Return the new coin balance
    return get_user_coins(user_id)
