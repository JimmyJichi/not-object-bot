# My Personal Discord Bot 🌠

A Discord bot that creates an engaging community experience with shooting star events, coin economy, and photo sharing features.

## Features

### 🌠 Shooting Star Events
- **Automated Events**: The bot generates 6 random shooting star events per day across specified channels
- **Time-based Schedule**: Events occur at random times throughout the day (UTC)
- **Interactive Gameplay**: Users must type the correct word to "catch" the shooting star
- **Rewards**: Successful catches award 100 coins
- **Visual Appeal**: Each event includes an embedded image and attractive Discord embeds

### 💰 Coin Economy System
- **Daily Rewards**: 
  - 200 coins for first message of the day (UTC)
  - 200 coins for daily check-in command
- **Starting Balance**: New users begin with 1000 coins
- **Commands**:
  - `/coins` - Check your coin balance
  - `/coins @user` - Check another user's balance
  - `/leaderboard` - View top 10 users by coins
  - `/daily` - Claim daily check-in reward

### 📸 Photo Sharing System
- **Random Photos**: Spend 1000 coins to get a random photo from a curated collection
- **Location Data**: Photos include GPS location information extracted from EXIF data
- **Progress Tracking**: Shows how many photos have been revealed vs. total available
- **Channel Restrictions**: Can be limited to specific channels
- **Automatic Management**: Revealed photos are moved to a separate directory

## Installation

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- Discord Server with appropriate permissions

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd shooting-star
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Create a `.env` file in the project root:
   ```env
   DISCORD_TOKEN=your_discord_bot_token_here
   SHOOTING_STAR_CHANNEL=channel_id_1,channel_id_2,channel_id_3
   PHOTO_CHANNEL=photo_channel_id
   PHOTO_MENTION_USER=user_id_to_mention_in_photos
   ```

5. **Prepare Photos Directory**
   - Add photos to the `photos/` directory
   
6. **Run the Bot**
   ```bash
   python bot.py
   ```

## Configuration

### Bot Permissions

The bot requires the following Discord permissions:
- Send Messages
- Embed Links
- Attach Files
- Read Message History
- Use Slash Commands

## How It Works

### Shooting Star Events
1. The bot generates a daily schedule with 6 random events
2. Each event has a predetermined time, channel, and catch word
3. Events are scheduled throughout the day (UTC)
4. When an event triggers, users have 60 seconds to type the correct word
5. Successful catches award 100 coins

### Coin System
- Users earn coins through various activities
- All coin transactions are stored in SQLite database
- Leaderboard shows top earners

### Photo System
- Photos are stored in the `photos/` directory
- EXIF data is extracted to show location information
- Photos are moved to `revealed/` after being shown
- GPS coordinates are reverse-geocoded to show city/country

## Dependencies

- `discord.py` - Discord API wrapper
- `python-dotenv` - Environment variable management
- `Pillow` - Image processing and EXIF data extraction
- `geopy` - GPS coordinate reverse geocoding