import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.database import init_database, can_earn_daily_message_reward, process_daily_message_reward

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

class NotObjectBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        """Called when the bot is starting up"""
        # Load cogs
        await self.load_extension('cogs.coins')
        await self.load_extension('cogs.shooting_star')
        await self.load_extension('cogs.photos')
        await self.load_extension('cogs.llm')
        
        # Sync commands
        # await self.tree.sync()

    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        init_database()
        
        # Start the shooting star task
        shooting_star_cog = self.get_cog('ShootingStarCog')
        if shooting_star_cog:
            shooting_star_cog.shooting_star_task.start()

bot = NotObjectBot()

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        await bot.process_commands(message)
        return

    # Check if this is the user's first message of the day (UTC) for coin reward
    user_id = message.author.id
    username = message.author.display_name
    
    if can_earn_daily_message_reward(user_id):
        # Award 200 coins for first message of the day
        process_daily_message_reward(user_id, username)
    
    # Process commands
    await bot.process_commands(message)

# Run the bot
if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))