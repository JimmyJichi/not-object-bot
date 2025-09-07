import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.database import init_database

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

class ShootingStarBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        """Called when the bot is starting up"""
        # Load cogs
        await self.load_extension('cogs.coins')
        await self.load_extension('cogs.shooting_star')
        await self.load_extension('cogs.photos')
        
        # Sync commands
        await self.tree.sync()

    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
        init_database()
        
        # Start the shooting star task
        shooting_star_cog = self.get_cog('ShootingStarCog')
        if shooting_star_cog:
            shooting_star_cog.shooting_star_task.start()

bot = ShootingStarBot()

@bot.event
async def on_message(message):
    # Handle !sync command for owner
    if message.content.lower() == '!sync' and message.author.id == int(os.getenv('OWNER_ID', 0)):
        try:
            await bot.tree.sync()
            await message.channel.send("✅ Command tree synced successfully!")
        except Exception as e:
            await message.channel.send(f"❌ Failed to sync command tree: {e}")
        return
    
    # Process commands
    await bot.process_commands(message)

# Run the bot
if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))