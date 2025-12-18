import discord
from discord import app_commands
from discord.ext import commands
import os
from datetime import datetime, timezone, timedelta
from utils.database import can_snap_today, process_snap


class SnapCog(commands.Cog):
    """Cog for handling daily snap photos with streak rewards"""
    
    def __init__(self, bot):
        self.bot = bot
        self.snaps_dir = "snaps"
        
        # Create snaps directory if it doesn't exist
        os.makedirs(self.snaps_dir, exist_ok=True)
    
    def get_next_utc_midnight_timestamp(self):
        """Get the Unix timestamp for the next UTC midnight"""
        now = datetime.now(timezone.utc)
        # Calculate next midnight UTC
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(next_midnight.timestamp())
    
    def generate_safe_filename(self, user_id, original_filename):
        """Generate a safe filename for the snap"""
        # Get file extension from original filename
        if original_filename and '.' in original_filename:
            ext = original_filename.rsplit('.', 1)[1]
            # Clean extension to be safe
            ext = ''.join(c for c in ext if c.isalnum() or c in '._-')
            if not ext:
                ext = 'jpg'
        else:
            ext = 'jpg'
        
        # Generate filename with timestamp and user_id
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        return f"snap_{user_id}_{timestamp}.{ext}"

    @app_commands.command(name='snap', description='Share a daily photo and earn streak rewards!')
    @app_commands.describe(photo='The photo to share')
    async def snap(self, interaction: discord.Interaction, photo: discord.Attachment):
        """Command to share a daily photo with streak rewards"""
        # Validate that the attachment is an image
        if not photo.content_type or not photo.content_type.startswith('image/'):
            embed = discord.Embed(
                title="❌ Invalid File",
                description="Please upload an image file (jpg, png, gif, etc.)",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        # Check if user can snap today
        can_snap, current_streak, _ = can_snap_today(user_id)
        
        if not can_snap:
            next_snap_time = self.get_next_utc_midnight_timestamp()
            embed = discord.Embed(
                title="⏰ Already Snapped Today",
                description=f"You've already shared a photo today! \n\nCome back <t:{next_snap_time}:R> (<t:{next_snap_time}>) to continue your streak!",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Defer the response to prevent timeout during processing
        await interaction.response.defer(ephemeral=True)
        
        # Process the snap and get reward
        reward, new_streak_days, new_balance = process_snap(user_id, username)
        
        # Get the snap channel ID from environment variable
        snap_channel_id = os.getenv('SNAP_CHANNEL_ID')
        
        if not snap_channel_id:
            embed = discord.Embed(
                title="❌ Configuration Error",
                description="Snap channel is not configured. Please contact an administrator.",
                color=0xff6b6b
            )
            await interaction.followup.send(embed=embed)
            return
        
        try:
            snap_channel = self.bot.get_channel(int(snap_channel_id))
            
            if not snap_channel:
                embed = discord.Embed(
                    title="❌ Channel Not Found",
                    description="The snap channel could not be found.",
                    color=0xff6b6b
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Download the image
            image_data = await photo.read()
            
            # Generate safe filename and save to local folder
            safe_filename = self.generate_safe_filename(user_id, photo.filename)
            local_file_path = os.path.join(self.snaps_dir, safe_filename)
            
            # Save image to local file
            with open(local_file_path, 'wb') as f:
                f.write(image_data)
            
            # Create embed for the snap channel
            snap_embed = discord.Embed(
                title="📸 Daily Snap",
                description=f"**{username}** shared a photo!",
                color=0x4ecdc4
            )
            streak_display = "1 day" if new_streak_days == 0 else f"{new_streak_days + 1} days"
            snap_embed.add_field(name="🔥 Streak", value=streak_display, inline=True)
            snap_embed.add_field(name="💰 Reward", value=f"+{reward} coins", inline=True)
            snap_embed.set_image(url=f"attachment://{safe_filename}")
            
            # Send to snap channel from local file
            with open(local_file_path, 'rb') as f:
                photo_file = discord.File(f, filename=safe_filename)
                sent_message = await snap_channel.send(embed=snap_embed, file=photo_file)
            
            # Create message link
            message_link = sent_message.jump_url
            
            # Create success message for the user
            embed = discord.Embed(
                title="✅ Snap Shared!",
                description=f"Your photo has been posted in {snap_channel.mention}!\n[View your snap]({message_link})",
                color=0x4ecdc4
            )
            embed.add_field(name="💰 Reward Earned", value=f"+{reward} coins", inline=True)
            streak_display = "1 day" if new_streak_days == 0 else f"{new_streak_days + 1} days"
            embed.add_field(name="🔥 Streak", value=streak_display, inline=True)
            embed.add_field(name="💳 New Balance", value=f"{new_balance} coins", inline=False)
            
            # Add streak info message
            if new_streak_days > 0:
                next_reward = min(25 * (new_streak_days + 1 + 1), 500)
                embed.add_field(
                    name="📈 Next Reward",
                    value=f"Share another photo tomorrow for {next_reward} coins!",
                    inline=False
                )
            
            embed.set_footer(text="Come back tomorrow (UTC) to continue your streak!")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to post your snap: {str(e)}",
                color=0xff6b6b
            )
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(SnapCog(bot))

