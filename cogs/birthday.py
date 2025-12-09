import discord
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timezone
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from utils.database import (
    set_user_birthday,
    get_user_birthday,
    get_all_active_birthdays,
    remove_user_birthday,
    add_coins,
    get_unique_timezones
)


async def month_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for month selection - shows list of all months"""
    months = [
        ("1", "January"), ("2", "February"), ("3", "March"), ("4", "April"),
        ("5", "May"), ("6", "June"), ("7", "July"), ("8", "August"),
        ("9", "September"), ("10", "October"), ("11", "November"), ("12", "December")
    ]
    
    if not current:
        # Show all months if no input
        return [
            app_commands.Choice(name=f"{num} - {name}", value=name)
            for num, name in months
        ][:25]
    
    current_lower = current.lower()
    # Filter months that match the input (by name or number)
    choices = []
    for num, name in months:
        if current_lower in name.lower() or current_lower == num or (current_lower.isdigit() and current_lower == num):
            choices.append(app_commands.Choice(name=f"{num} - {name}", value=name))
    
    # If no matches found but user typed a number, show that number's month
    if not choices and current_lower.isdigit() and 1 <= int(current_lower) <= 12:
        num = current_lower
        name = months[int(num) - 1][1]
        choices.append(app_commands.Choice(name=f"{num} - {name}", value=name))
    
    return choices[:25]  # Discord limits to 25 choices


async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for timezone selection - shows list of available timezones"""
    # Map timezones to display names
    timezones = {
        "America/Los_Angeles": "Los Angeles (PST/PDT)",
        "America/Phoenix": "Phoenix (MST)",
        "America/Chicago": "Chicago (CST/CDT)",
        "America/New_York": "New York (EST/EDT)",
        "America/Halifax": "Halifax (AST/ADT)",
        "Europe/London": "London (GMT/BST)",
        "Europe/Paris": "Paris (CET/CEST)",
        "Europe/Helsinki": "Helsinki (EET/EEST)",
        "Europe/Moscow": "Moscow (MSK)",
        "Asia/Shanghai": "Shanghai (CST)",
        "Asia/Tokyo": "Tokyo (JST)",
        "Australia/Perth": "Perth (AWST)",
        "Australia/Darwin": "Darwin (ACST)",
        "Australia/Adelaide": "Adelaide (ACST/ACDT)",
        "Australia/Brisbane": "Brisbane (AEST)",
        "Australia/Sydney": "Sydney (AEST/AEDT)",
        "Pacific/Auckland": "Auckland (NZST/NZDT)",
        "UTC": "UTC (Coordinated Universal Time)"
    }
    
    if not current:
        # Show all timezones if no input
        return [
            app_commands.Choice(name=display_name, value=tz_name)
            for tz_name, display_name in timezones.items()
        ][:25]
    
    current_lower = current.lower()
    # Filter timezones that match the input
    choices = []
    for tz_name, display_name in timezones.items():
        if (current_lower in display_name.lower() or 
            current_lower in tz_name.lower() or
            current_lower in tz_name.split('/')[-1].lower()):
            choices.append(app_commands.Choice(name=display_name, value=tz_name))
    
    return choices[:25]  # Discord limits to 25 choices


class BirthdayCog(commands.Cog):
    """Cog for handling birthday functionality"""
    
    # Command group as class attribute for decorators
    birthday_group = app_commands.Group(name="birthday", description="Manage birthdays")
    
    # Coin reward amounts
    FIRST_TIME_SET_REWARD = 1000
    BIRTHDAY_REWARD = 5000
    
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.birthday_channel_id = int(os.getenv('BIRTHDAY_CHANNEL_ID')) if os.getenv('BIRTHDAY_CHANNEL_ID') else None
        self.sent_birthdays_today = {}  # Track which user IDs we've sent birthday messages to (key: timezone, value: set of user_ids)
        self.scheduled_timezones = set()  # Track which timezones have scheduled jobs
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Start the scheduler when the cog is ready"""
        if not self.scheduler.running:
            self.scheduler.start()
            # Schedule jobs for all existing timezones
            await self.schedule_all_timezones()
            print("Birthday scheduler started")

    async def schedule_all_timezones(self):
        """Schedule birthday checks for all unique timezones in the database"""
        timezones = get_unique_timezones()
        for tz_name in timezones:
            self.schedule_timezone_job(tz_name)

    def schedule_timezone_job(self, tz_name: str):
        """Schedule a job to check birthdays at midnight in a specific timezone"""
        if tz_name in self.scheduled_timezones:
            return  # Already scheduled
        
        try:
            # Get the timezone object
            tz = pytz.timezone(tz_name)
            
            # Schedule job to run at midnight in this timezone
            job_id = f'birthday_check_{tz_name}'
            self.scheduler.add_job(
                self.check_birthdays_for_timezone,
                trigger=CronTrigger(hour=0, minute=0, timezone=tz),
                id=job_id,
                replace_existing=True,
                args=[tz_name]
            )
            self.scheduled_timezones.add(tz_name)
            print(f"Scheduled birthday check for timezone: {tz_name}")
        except Exception as e:
            print(f"Error scheduling job for timezone {tz_name}: {e}")

    async def check_birthdays_for_timezone(self, tz_name: str):
        """Check for birthdays in a specific timezone at midnight"""
        if not self.birthday_channel_id:
            return
        
        channel = self.bot.get_channel(self.birthday_channel_id)
        if not channel:
            return
        
        # Get all active birthdays for this timezone
        all_birthdays = get_all_active_birthdays()
        birthdays = [b for b in all_birthdays if b['timezone'] == tz_name]
        
        if not birthdays:
            return
        
        # Get current date in this timezone
        try:
            tz = pytz.timezone(tz_name)
            now_utc = datetime.now(timezone.utc)
            now_in_tz = now_utc.astimezone(tz)
            
            # Initialize tracking for this timezone if needed
            if tz_name not in self.sent_birthdays_today:
                self.sent_birthdays_today[tz_name] = set()
            
            # Get the set of users we've already sent to today for this timezone
            sent_today = self.sent_birthdays_today[tz_name]
            
            # Check each birthday
            for birthday in birthdays:
                try:
                    # Skip if we already sent to this user today in this timezone
                    if birthday['user_id'] in sent_today:
                        continue
                    
                    # Check if today is the birthday
                    if now_in_tz.month == birthday['month'] and now_in_tz.day == birthday['day']:
                        await self.send_birthday_message(channel, birthday)
                        # Mark as sent for this timezone
                        sent_today.add(birthday['user_id'])
                except Exception as e:
                    print(f"Error checking birthday for user {birthday['user_id']}: {e}")
        except Exception as e:
            print(f"Error checking birthdays for timezone {tz_name}: {e}")
        except Exception as e:
            print(f"Error checking birthdays for timezone {tz_name}: {e}")

    async def send_birthday_message(self, channel, birthday):
        """Send a birthday message and give coins"""
        user_id = birthday['user_id']
        user = self.bot.get_user(user_id)
        
        if not user:
            return
        
        # Calculate age if year is provided
        age_text = ""
        if birthday['year']:
            try:
                tz = pytz.timezone(birthday['timezone'])
                now_in_tz = datetime.now(timezone.utc).astimezone(tz)
                age = now_in_tz.year - birthday['year']
                age_text = f" They're turning {age} today! 🎂"
            except:
                pass
        
        # Give coins on birthday
        from utils.database import get_user_coins
        username = user.display_name if user else f"User {user_id}"
        add_coins(user_id, username, self.BIRTHDAY_REWARD)
        new_balance = get_user_coins(user_id)
        
        # Create birthday message
        embed = discord.Embed(
            title="🎉 Happy Birthday! 🎉",
            description=f"Happy birthday to {user.mention}!{age_text}",
            color=0xffd700
        )
        embed.add_field(
            name="🎁 Birthday Reward",
            value=f"You received **{self.BIRTHDAY_REWARD} coins**!\nTotal coins: **{new_balance}**",
            inline=False
        )
        embed.set_footer(text="Have an amazing day! 🎈")
        
        await channel.send(embed=embed)
        print(f"Sent birthday message for user {user_id} ({username})")

    @birthday_group.command(name="set")
    @app_commands.describe(
        month="Birth month (1-12 or month name)",
        day="Birth day (1-31)",
        year="Birth year (optional)",
        timezone_name="Timezone (select from list or type any valid timezone, defaults to UTC)"
    )
    @app_commands.autocomplete(month=month_autocomplete, timezone_name=timezone_autocomplete)
    async def birthday_set(self, interaction: discord.Interaction, month: str, day: int, year: int = None, timezone_name: str = None):
        """Set or update your birthday"""
        # Month names mapping
        month_names = {
            "january": 1, "jan": 1, "1": 1,
            "february": 2, "feb": 2, "2": 2,
            "march": 3, "mar": 3, "3": 3,
            "april": 4, "apr": 4, "4": 4,
            "may": 5, "5": 5,
            "june": 6, "jun": 6, "6": 6,
            "july": 7, "jul": 7, "7": 7,
            "august": 8, "aug": 8, "8": 8,
            "september": 9, "sep": 9, "sept": 9, "9": 9,
            "october": 10, "oct": 10, "10": 10,
            "november": 11, "nov": 11, "11": 11,
            "december": 12, "dec": 12, "12": 12
        }
        
        # Parse month
        month_lower = month.lower().strip()
        if month_lower not in month_names:
            embed = discord.Embed(
                title="❌ Invalid Month",
                description="Month must be a number (1-12) or a month name (e.g., January, Feb, March).",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        month_num = month_names[month_lower]
        
        # Validate day
        if day is None:
            embed = discord.Embed(
                title="❌ Missing Required Fields",
                description="Day is required.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not (1 <= day <= 31):
            embed = discord.Embed(
                title="❌ Invalid Day",
                description="Day must be between 1 and 31.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validate date (e.g., Feb 30 doesn't exist)
        try:
            test_date = datetime(2000 if year is None else year, month_num, day)
        except ValueError:
            month_names_list = ["", "January", "February", "March", "April", "May", "June",
                              "July", "August", "September", "October", "November", "December"]
            embed = discord.Embed(
                title="❌ Invalid Date",
                description=f"The date {month_names_list[month_num]} {day} is not valid.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validate timezone if provided
        tz = pytz.UTC  # Default
        if timezone_name:
            try:
                tz = pytz.timezone(timezone_name)
            except pytz.exceptions.UnknownTimeZoneError:
                embed = discord.Embed(
                    title="❌ Invalid Timezone",
                    description=f"Timezone '{timezone_name}' is not recognized. Please use a valid timezone name (e.g., 'America/New_York', 'Europe/London', 'UTC').",
                    color=0xff6b6b
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        else:
            timezone_name = 'UTC'
        
        # Set birthday
        user_id = interaction.user.id
        is_first_time = set_user_birthday(user_id, month_num, day, year, timezone_name)
        
        # Schedule a job for this timezone if it doesn't exist
        if timezone_name not in self.scheduled_timezones:
            self.schedule_timezone_job(timezone_name)
        
        # Format date for display
        month_names_list = ["", "January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"]
        date_str = f"{month_names_list[month_num]} {day}"
        if year:
            date_str += f", {year}"
        
        # Give coins if first time
        if is_first_time:
            from utils.database import get_user_coins
            username = interaction.user.display_name
            add_coins(user_id, username, self.FIRST_TIME_SET_REWARD)
            new_balance = get_user_coins(user_id)
            
            embed = discord.Embed(
                title="✅ Birthday Set!",
                description=f"Your birthday has been set to **{date_str}** ({timezone_name}).",
                color=0x4ecdc4
            )
            embed.add_field(
                name="💰 Reward",
                value=f"You received **{self.FIRST_TIME_SET_REWARD} coins**!\nTotal coins: **{new_balance}**",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="✅ Birthday Updated!",
                description=f"Your birthday has been updated to **{date_str}** ({timezone_name}).",
                color=0x4ecdc4
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @birthday_group.command(name="get")
    @app_commands.describe(
        user="User to check birthday for (optional, shows all if not specified)"
    )
    async def birthday_get(self, interaction: discord.Interaction, user: discord.User = None):
        """View a user's birthday"""
        if user is None:
            # Get all birthdays
            birthdays = get_all_active_birthdays()
            
            if not birthdays:
                embed = discord.Embed(
                    title="📅 Birthdays",
                    description="No birthdays have been set yet.",
                    color=0xffd700
                )
                await interaction.response.send_message(embed=embed)
                return
            
            # Sort by month and day
            birthdays.sort(key=lambda x: (x['month'], x['day']))
            
            embed = discord.Embed(
                title="📅 All Birthdays",
                color=0xffd700
            )
            
            # Group by month for better display
            month_names = ["", "January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"]
            
            birthday_list = []
            for bday in birthdays:
                try:
                    user_obj = self.bot.get_user(bday['user_id'])
                    username = user_obj.mention if user_obj else f"User {bday['user_id']}"
                    date_str = f"{month_names[bday['month']]} {bday['day']}"
                    if bday['year']:
                        date_str += f", {bday['year']}"
                    birthday_list.append(f"{username}: {date_str}")
                except:
                    pass
            
            if birthday_list:
                # Split into chunks if too long
                description = "\n".join(birthday_list[:20])  # Limit to 20 for embed
                if len(birthday_list) > 20:
                    description += f"\n... and {len(birthday_list) - 20} more"
                embed.description = description
            else:
                embed.description = "No birthdays found."
            
            await interaction.response.send_message(embed=embed)
        else:
            # Get specific user's birthday
            birthday = get_user_birthday(user.id)
            
            if not birthday:
                embed = discord.Embed(
                    title="📅 Birthday",
                    description=f"{user.mention} hasn't set their birthday yet.",
                    color=0xffd700
                )
                await interaction.response.send_message(embed=embed)
                return
            
            month_names = ["", "January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"]
            
            date_str = f"{month_names[birthday['month']]} {birthday['day']}"
            if birthday['year']:
                date_str += f", {birthday['year']}"
            
            embed = discord.Embed(
                title=f"📅 {user.display_name}'s Birthday",
                description=f"**{date_str}**",
                color=0xffd700
            )
            await interaction.response.send_message(embed=embed)

    @birthday_group.command(name="remove")
    async def birthday_remove(self, interaction: discord.Interaction):
        """Remove your birthday"""
        user_id = interaction.user.id
        birthday = get_user_birthday(user_id)
        
        if not birthday:
            embed = discord.Embed(
                title="❌ No Birthday Set",
                description="You don't have a birthday set to remove.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        remove_user_birthday(user_id)
        
        embed = discord.Embed(
            title="✅ Birthday Removed",
            description="Your birthday has been removed.",
            color=0x4ecdc4
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self.scheduler.running:
            self.scheduler.shutdown()


async def setup(bot):
    await bot.add_cog(BirthdayCog(bot))

