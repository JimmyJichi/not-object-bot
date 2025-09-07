import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_user_coins, get_leaderboard, can_daily_checkin, perform_daily_checkin


class CoinsCog(commands.Cog):
    """Cog for handling coin-related commands"""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='coins', description='Check your coin balance')
    async def check_coins(self, interaction: discord.Interaction, user: discord.User = None):
        """Check your coin balance or another user's balance"""
        # If no user specified, check the command user's balance
        if user is None:
            user = interaction.user
        
        user_id = user.id
        coins = get_user_coins(user_id)
        
        embed = discord.Embed(
            title="💰 Coin Balance",
            description=f"{user.mention} has **{coins} coins**!",
            color=0xffd700
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='leaderboard', description='Show the top 10 users by coins')
    async def leaderboard(self, interaction: discord.Interaction):
        """Show the top 10 users by coins"""
        results = get_leaderboard(10)
        
        if not results:
            embed = discord.Embed(
                title="🏆 Leaderboard",
                description="No users have earned coins yet!",
                color=0xffd700
            )
        else:
            embed = discord.Embed(
                title="🏆 Coin Leaderboard",
                color=0xffd700
            )
            
            for i, (username, coins) in enumerate(results, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                embed.add_field(
                    name=f"{medal} {username}",
                    value=f"**{coins} coins**",
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='daily', description='Check in daily to earn 200 coins!')
    async def daily_checkin(self, interaction: discord.Interaction):
        """Daily check-in command that gives users 200 coins once per day (UTC)"""
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        # Check if user can perform daily check-in
        if not can_daily_checkin(user_id):
            embed = discord.Embed(
                title="⏰ Already Checked In Today",
                description="You've already claimed your daily coins! Come back tomorrow (UTC) for another 200 coins!",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Perform the daily check-in
        new_balance = perform_daily_checkin(user_id, username)
        
        embed = discord.Embed(
            title="🎉 Daily Check-in Complete!",
            description=f"**+200 coins** added to your balance!\n\nYour new balance: **{new_balance} coins**",
            color=0x4ecdc4
        )
        embed.set_footer(text="Come back tomorrow (UTC) for another daily reward!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(CoinsCog(bot))
