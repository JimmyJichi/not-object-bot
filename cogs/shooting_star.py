import discord
from discord.ext import commands, tasks
import random
import asyncio
import datetime
import os
import json
from utils.database import add_coins


class ShootingStarCog(commands.Cog):
    """Cog for handling shooting star events"""
    
    def __init__(self, bot):
        self.bot = bot
        self.shooting_star_active = False
        self.current_message = ""
        self.current_channel = None
        self.shooting_star_msg = None  # Store reference to the shooting star message
        self.possible_messages = ["inertia", "bubbly", "object", "slime", "ithaca", "betty"]
        self.SCHEDULE_FILE = 'shooting_star_schedule.json'

    def load_schedule(self):
        """Load schedule from file"""
        try:
            with open(self.SCHEDULE_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def save_schedule(self, schedule):
        """Save schedule to file"""
        with open(self.SCHEDULE_FILE, 'w') as f:
            json.dump(schedule, f, indent=2)

    def generate_daily_schedule(self, channel_ids):
        """Generate a new daily schedule with predetermined channels and messages"""
        today = datetime.date.today().isoformat()
        
        # Shuffle channels to randomize the order
        shuffled_channels = channel_ids.copy()
        random.shuffle(shuffled_channels)
        
        # Shuffle messages to ensure each one is used once
        shuffled_messages = self.possible_messages.copy()
        random.shuffle(shuffled_messages)
        
        schedule = {
            'date': today,
            'events': []
        }

        used_hours = set()
        
        # Generate 6 random times and assign channels and messages
        for i in range(6):
            # Random hour between 0 and 23
            hour = random.randint(0, 23)
            while hour in used_hours:
                hour = random.randint(0, 23)
            used_hours.add(hour)
            
            # Random minute
            minute = random.randint(0, 59)
            
            # Use modulo to cycle through channels if there are fewer than 6
            channel_id = shuffled_channels[i % len(shuffled_channels)]
            
            # Use each message once (shuffled order)
            message = shuffled_messages[i % len(shuffled_messages)]
            
            event = {
                'time': f"{hour:02d}:{minute:02d}",
                'channel_id': channel_id,
                'message': message,
                'completed': False
            }
            schedule['events'].append(event)
        
        # Sort events by time
        schedule['events'].sort(key=lambda x: x['time'])
        
        return schedule

    def get_current_schedule(self, channel_ids):
        """Get or generate the current day's schedule"""
        schedule = self.load_schedule()
        today = datetime.date.today().isoformat()
        
        # If no schedule exists or it's for a different day, generate new one
        if not schedule or schedule.get('date') != today:
            schedule = self.generate_daily_schedule(channel_ids)
            self.save_schedule(schedule)
            event_descriptions = []
            for e in schedule['events']:
                event_descriptions.append(f"{e['time']} (Channel {e['channel_id']}, Message: {e['message']})")
            print("Generated daily schedule:")
            for desc in event_descriptions:
                print(f"  {desc}")
        
        return schedule

    def get_next_event(self, schedule):
        """Get the next uncompleted event"""
        now = datetime.datetime.now()
        
        for event in schedule['events']:
            if not event['completed']:
                # Parse event time
                hour, minute = map(int, event['time'].split(':'))
                event_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                if event_time <= now:
                    return event
        
        return None

    def mark_event_completed(self, schedule, event):
        """Mark an event as completed and save the schedule"""
        for e in schedule['events']:
            if e['time'] == event['time'] and e['channel_id'] == event['channel_id']:
                e['completed'] = True
                break
        self.save_schedule(schedule)

    @tasks.loop(minutes=1)  # Check every minute
    async def shooting_star_task(self):
        """Main task loop for shooting star events"""
        # Get the channel IDs from environment variable
        channel_ids_str = os.getenv('SHOOTING_STAR_CHANNEL', '')
        if not channel_ids_str:
            print("Please set CHANNEL_IDS in your .env file (comma-separated list of channel IDs)")
            return
        
        # Parse channel IDs from comma-separated string
        try:
            channel_ids = [int(cid.strip()) for cid in channel_ids_str.split(',')]
        except ValueError:
            print("Invalid CHANNEL_IDS format. Please use comma-separated channel IDs")
            return
        
        # Get current schedule
        schedule = self.get_current_schedule(channel_ids)
        
        # Check if it's time for the next event
        next_event = self.get_next_event(schedule)
        if not next_event:
            return  # No more events today
        
        # Mark this event as completed
        self.mark_event_completed(schedule, next_event)
        
        # Get the predetermined channel
        channel = self.bot.get_channel(next_event['channel_id'])
        if not channel:
            print(f"Could not find channel with ID {next_event['channel_id']}")
            return
        
        self.current_channel = channel
        self.current_message = next_event['message']  # Use the predetermined message
        self.shooting_star_active = True
        
        now = datetime.datetime.now()
        print(f"Starting shooting star event in channel {channel.name} at {now.strftime('%H:%M:%S')} (scheduled for {next_event['time']}, message: {self.current_message})")
        
        embed = discord.Embed(
            title="🌠 A Shooting Star Appears!",
            description="The night sky is alight as a shooting star blazes through the heavens! ✨\nCatch it before it fades away and earn some shiny coins! 💰",
            color=0x00ffff
        )
        embed.add_field(
            name="🌟 Catch the Shooting Star!",
            value=f"Type `{self.current_message}` to catch it! 🌟\nHurry, time's running out! ⏳",
            inline=False
        )
        embed.set_footer(text="You have 60 seconds to catch it!")
        
        # Attach the image to the embed
        with open('image.png', 'rb') as f:
            file = discord.File(f, filename='shooting_star.png')
            embed.set_image(url='attachment://shooting_star.png')
            self.shooting_star_msg = await channel.send(embed=embed, file=file)
        
        # Wait 60 seconds for responses
        await asyncio.sleep(60)
        
        if self.shooting_star_active:
            # No one caught it - delete the shooting star message
            if self.shooting_star_msg:
                try:
                    await self.shooting_star_msg.delete()
                except discord.NotFound:
                    pass  # Message already deleted
            self.shooting_star_active = False

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle shooting star catching messages"""
        # Ignore bot messages
        if message.author == self.bot.user:
            return
        
        # Check if shooting star is active and message matches
        if self.shooting_star_active and message.content.lower() == self.current_message.lower():
            self.shooting_star_active = False
                        
            # Add coins to the user
            user_id = message.author.id
            username = message.author.display_name
            add_coins(user_id, username, 100)
            
            # Get updated coin count
            from utils.database import get_user_coins
            total_coins = get_user_coins(user_id)
            
            embed = discord.Embed(
                title="🌟 Shooting Star Caught!",
                description=f"Congratulations {message.author.mention}! You caught the shooting star! ✨",
                color=0x00ff00
            )
            embed.add_field(
                name="💰 Reward",
                value=f"You earned **100 coins**!\nTotal coins: **{total_coins}**",
                inline=False
            )
            embed.set_footer(text=f"Caught at {datetime.datetime.now(datetime.UTC).strftime('%H:%M:%S')} UTC")
            
            await message.channel.send(embed=embed)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.shooting_star_task.cancel()


async def setup(bot):
    await bot.add_cog(ShootingStarCog(bot))
