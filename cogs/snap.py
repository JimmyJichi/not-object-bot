import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime, timezone, timedelta
from utils.database import can_snap_today, process_snap


class SnapCog(commands.Cog):
    """Cog for handling daily snap photos with streak rewards"""

    def __init__(self, bot):
        self.bot = bot
        self.s3 = boto3.client(
            's3',
            endpoint_url=os.getenv('B2_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('B2_KEY_ID'),
            aws_secret_access_key=os.getenv('B2_APPLICATION_KEY'),
        )
        self.bucket_name = os.getenv('B2_BUCKET_NAME')
        self.public_url_base = os.getenv('B2_PUBLIC_URL_BASE', '').rstrip('/')

    def get_next_utc_midnight_timestamp(self):
        now = datetime.now(timezone.utc)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(next_midnight.timestamp())

    def generate_safe_filename(self, user_id, original_filename):
        if original_filename and '.' in original_filename:
            ext = original_filename.rsplit('.', 1)[1]
            ext = ''.join(c for c in ext if c.isalnum() or c in '._-')
            if not ext:
                ext = 'jpg'
        else:
            ext = 'jpg'
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        return f"snap_{user_id}_{timestamp}.{ext}"

    async def upload_to_b2(self, image_data: bytes, filename: str, content_type: str) -> str:
        await asyncio.to_thread(
            self.s3.put_object,
            Bucket=self.bucket_name,
            Key=filename,
            Body=image_data,
            ContentType=content_type,
        )
        return f"{self.public_url_base}/{filename}"

    @app_commands.command(name='snap', description='Share a daily photo and earn streak rewards!')
    @app_commands.describe(photo='The photo to share')
    async def snap(self, interaction: discord.Interaction, photo: discord.Attachment):
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

        can_snap, _, _ = can_snap_today(user_id)

        if not can_snap:
            next_snap_time = self.get_next_utc_midnight_timestamp()
            embed = discord.Embed(
                title="⏰ Already Snapped Today",
                description=f"You've already shared a photo today! \n\nCome back <t:{next_snap_time}:R> (<t:{next_snap_time}>) to continue your streak!",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        reward, new_streak_days, new_balance = process_snap(user_id, username)

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

            image_data = await photo.read()
            safe_filename = self.generate_safe_filename(user_id, photo.filename)
            image_url = await self.upload_to_b2(image_data, safe_filename, photo.content_type)

            snap_embed = discord.Embed(
                title="📸 Daily Snap",
                description=f"**{username}** shared a photo!",
                color=0x4ecdc4
            )
            streak_display = "1 day" if new_streak_days == 0 else f"{new_streak_days + 1} days"
            snap_embed.add_field(name="🔥 Streak", value=streak_display, inline=True)
            snap_embed.add_field(name="💰 Reward", value=f"+{reward} coins", inline=True)
            snap_embed.set_image(url=image_url)
            snap_embed.add_field(name="🔗 Original", value=f"[Download]({image_url})", inline=False)

            sent_message = await snap_channel.send(embed=snap_embed)
            message_link = sent_message.jump_url

            embed = discord.Embed(
                title="✅ Snap Shared!",
                description=f"Your photo has been posted in {snap_channel.mention}!\n[View your snap]({message_link})",
                color=0x4ecdc4
            )
            embed.add_field(name="💰 Reward Earned", value=f"+{reward} coins", inline=True)
            streak_display = "1 day" if new_streak_days == 0 else f"{new_streak_days + 1} days"
            embed.add_field(name="🔥 Streak", value=streak_display, inline=True)
            embed.add_field(name="💳 New Balance", value=f"{new_balance} coins", inline=False)

            if new_streak_days > 0:
                next_reward = min(25 * (new_streak_days + 1 + 1), 500)
                embed.add_field(
                    name="📈 Next Reward",
                    value=f"Share another photo tomorrow for {next_reward} coins!",
                    inline=False
                )

            embed.set_footer(text="Come back tomorrow (UTC) to continue your streak!")
            await interaction.followup.send(embed=embed)

        except (BotoCoreError, ClientError) as e:
            embed = discord.Embed(
                title="❌ Upload Failed",
                description=f"Failed to upload your photo: {str(e)}",
                color=0xff6b6b
            )
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
