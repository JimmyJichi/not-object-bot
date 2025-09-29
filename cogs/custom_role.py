import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_user_coins, spend_coins, get_user_custom_role, create_user_custom_role, delete_user_custom_role, refund_coins
import os


class CustomRoleCog(commands.Cog):
    """Cog for handling custom role commands"""
    
    # Cost for creating a custom role
    CUSTOM_ROLE_COST = 2500
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='customrole', description=f'Create a custom role for {CUSTOM_ROLE_COST} coins')
    @app_commands.describe(
        text='The name of your custom role',
        color='The color of your role (hex code like #FF0000 or color name like red)'
    )
    async def create_custom_role(self, interaction: discord.Interaction, text: str, color: str):
        """Create a custom role for the user"""
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        # Check if user has enough coins
        current_coins = get_user_coins(user_id)
        if current_coins < self.CUSTOM_ROLE_COST:
            embed = discord.Embed(
                title="❌ Insufficient Coins",
                description=f"You need **{self.CUSTOM_ROLE_COST} coins** to create a custom role!\nYou currently have **{current_coins} coins**.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validate role name length
        if len(text) > 32:
            embed = discord.Embed(
                title="❌ Invalid Role Name",
                description="Role name must be 32 characters or less.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validate role name characters (Discord allows letters, numbers, spaces, and some special chars)
        if not all(c.isalnum() or c.isspace() or c in '-_' for c in text):
            embed = discord.Embed(
                title="❌ Invalid Role Name",
                description="Role name can only contain letters, numbers, spaces, hyphens, and underscores.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Parse color
        try:
            # Try to parse as hex color
            if color.startswith('#'):
                color_value = int(color[1:], 16)
            else:
                # Try to parse as color name
                color_lower = color.lower()
                color_map = {
                    'red': 0xff0000,
                    'green': 0x00ff00,
                    'blue': 0x0000ff,
                    'yellow': 0xffff00,
                    'orange': 0xffa500,
                    'purple': 0x800080,
                    'pink': 0xffc0cb,
                    'cyan': 0x00ffff,
                    'white': 0xffffff,
                    'black': 0x000000,
                    'gray': 0x808080,
                    'grey': 0x808080,
                    'brown': 0xa52a2a,
                    'lime': 0x00ff00,
                    'magenta': 0xff00ff,
                    'navy': 0x000080,
                    'teal': 0x008080,
                    'olive': 0x808000,
                    'maroon': 0x800000,
                    'silver': 0xc0c0c0,
                    'gold': 0xffd700
                }
                color_value = color_map.get(color_lower, 0x00ff00)  # Default to green if not found
        except ValueError:
            embed = discord.Embed(
                title="❌ Invalid Color",
                description="Please provide a valid hex color (like #FF0000) or color name (like red).",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check if user already has a custom role
        existing_role_data = get_user_custom_role(user_id)
        old_role = None
        if existing_role_data:
            old_role_id = existing_role_data[0]
            old_role = interaction.guild.get_role(old_role_id)
        
        # Spend coins
        if not spend_coins(user_id, username, self.CUSTOM_ROLE_COST):
            embed = discord.Embed(
                title="❌ Transaction Failed",
                description="Failed to spend coins. Please try again.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Delete old role if it exists
            if old_role:
                await old_role.delete()
                delete_user_custom_role(user_id)            
                
            # Create new role
            new_role = await interaction.guild.create_role(
                name=text,
                color=discord.Color(color_value),
                mentionable=False,
                reason=f"Custom role created by {username}"
            )

            all_roles = await interaction.guild.fetch_roles()
            num_roles = len(all_roles)

            await new_role.edit(position=num_roles - 2)
            
            # Assign role to user
            await interaction.user.add_roles(new_role, reason="Custom role assignment")
            
            # Store in database
            create_user_custom_role(user_id, new_role.id, text, color_value)
            
            # Get new coin balance
            new_balance = get_user_coins(user_id)
            
            embed = discord.Embed(
                title="✅ Custom Role Created!",
                description=f"**{text}** role has been created and assigned to you!\n\n💰 **Cost:** {self.CUSTOM_ROLE_COST} coins\n💳 **Balance:** {new_balance} coins",
                color=color_value
            )

            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission Error",
                description="I don't have permission to create roles or manage roles in this server.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            # Refund the coins since we couldn't create the role
            refund_coins(user_id, username, self.CUSTOM_ROLE_COST)
            
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="❌ Error Creating Role",
                description=f"Failed to create role: {str(e)}",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            # Refund the coins since we couldn't create the role
            refund_coins(user_id, username, self.CUSTOM_ROLE_COST)

    @app_commands.command(name='removerole', description='[ADMIN] Remove a user\'s custom role and refund their coins')
    @app_commands.describe(
        user='The user whose custom role to remove',
        reason='Reason for removing the role'
    )
    async def remove_custom_role(self, interaction: discord.Interaction, user: discord.User, reason: str):
        """Admin command to remove a user's custom role and refund their coins"""
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You need administrator permissions to use this command.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        user_id = user.id
        username = user.display_name
        
        # Check if user has a custom role
        existing_role_data = get_user_custom_role(user_id)
        if not existing_role_data:
            embed = discord.Embed(
                title="❌ No Custom Role Found",
                description=f"{user.mention} doesn't have a custom role to remove.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        role_id, role_name, role_color = existing_role_data
        custom_role = interaction.guild.get_role(role_id)
        
        try:
            # Remove role from user if they still have it
            member = interaction.guild.get_member(user_id)
            if member and custom_role in member.roles:
                await member.remove_roles(custom_role, reason=f"Custom role removed by {interaction.user.display_name}: {reason}")
            
            # Delete the role from the server
            if custom_role:
                await custom_role.delete(reason=f"Custom role removed by {interaction.user.display_name}: {reason}")
            
            # Remove from database
            delete_user_custom_role(user_id)
            
            # Refund coins
            refund_coins(user_id, username, self.CUSTOM_ROLE_COST)
            
            # Get new balance
            new_balance = get_user_coins(user_id)
            
            embed = discord.Embed(
                title="🗑️ Custom Role Removed",
                description=f"**{role_name}** role has been removed from {user.mention}!\n\n💰 **Refunded:** {self.CUSTOM_ROLE_COST} coins\n💳 **New Balance:** {new_balance} coins",
                color=0x4ecdc4
            )
            embed.add_field(
                name="Reason",
                value=reason,
                inline=False
            )
            embed.set_footer(text=f"Removed by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission Error",
                description="I don't have permission to manage roles in this server.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="❌ Error Removing Role",
                description=f"Failed to remove role: {str(e)}",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(CustomRoleCog(bot))
