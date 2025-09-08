import sqlite3


def init_database():
    """Initialize the database with the users table"""
    conn = sqlite3.connect('not_object.db')
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_messages (
            user_id INTEGER PRIMARY KEY,
            last_message_date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    conn.commit()
    conn.close()


def get_user_coins(user_id):
    """Get the coin balance for a specific user, creating them with 1000 coins if they don't exist"""
    conn = sqlite3.connect('not_object.db')
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        # User exists, return their coins
        conn.close()
        return result[0]
    else:
        # User doesn't exist, create them with 1000 coins
        cursor.execute('INSERT INTO users (user_id, username, coins) VALUES (?, ?, ?)', 
                      (user_id, "Unknown", 1000))
        conn.commit()
        conn.close()
        return 1000


def add_coins(user_id, username, amount):
    """Add coins to a user's balance, giving new users 1000 coins base"""
    conn = sqlite3.connect('not_object.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, coins)
        VALUES (?, ?, COALESCE((SELECT coins FROM users WHERE user_id = ?), 1000) + ?)
    ''', (user_id, username, user_id, amount))
    conn.commit()
    conn.close()


def remove_coins(user_id, username, amount):
    """Remove coins from a user's balance (minimum 0), giving new users 1000 coins base"""
    conn = sqlite3.connect('not_object.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, coins)
        VALUES (?, ?, MAX(COALESCE((SELECT coins FROM users WHERE user_id = ?), 1000) - ?, 0))
    ''', (user_id, username, user_id, amount))
    conn.commit()
    conn.close()


def spend_coins(user_id, username, amount):
    """Spend coins from a user's balance. Returns True if successful, False if insufficient funds"""
    conn = sqlite3.connect('not_object.db')
    cursor = conn.cursor()
    
    # Check current balance (this will create user with 1000 coins if they don't exist)
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
    conn = sqlite3.connect('not_object.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, coins FROM users ORDER BY coins DESC LIMIT ?', (limit,))
    results = cursor.fetchall()
    conn.close()
    return results


def can_daily_checkin(user_id):
    """Check if a user can perform a daily check-in (based on UTC date)"""
    from datetime import datetime, timezone
    
    conn = sqlite3.connect('not_object.db')
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
    
    conn = sqlite3.connect('not_object.db')
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


def can_earn_daily_message_reward(user_id):
    """Check if a user can earn coins for their first message of the day (based on UTC date)"""
    from datetime import datetime, timezone
    
    conn = sqlite3.connect('not_object.db')
    cursor = conn.cursor()
    
    # Get the last message date
    cursor.execute('SELECT last_message_date FROM daily_messages WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if not result:
        return True  # User has never sent a message
    
    last_message = result[0]
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    return last_message != today_utc


def process_daily_message_reward(user_id, username):
    """Process daily message reward for a user and return the new coin balance"""
    from datetime import datetime, timezone
    
    conn = sqlite3.connect('not_object.db')
    cursor = conn.cursor()
    
    # Add coins
    add_coins(user_id, username, 200)
    
    # Update message date
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    cursor.execute('''
        INSERT OR REPLACE INTO daily_messages (user_id, last_message_date)
        VALUES (?, ?)
    ''', (user_id, today_utc))
    
    conn.commit()
    conn.close()
    
    # Return the new coin balance
    return get_user_coins(user_id)
