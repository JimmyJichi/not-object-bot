import discord
from discord.ext import commands, tasks
from discord import app_commands
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from utils.database import (
    add_sotd_song,
    get_random_unused_song,
    mark_song_as_used,
    can_add_song
)


class SotdCog(commands.Cog):
    """Cog for Song of the Day functionality"""
    
    def __init__(self, bot):
        self.bot = bot
        self.client_id = os.getenv('SPOTIFY_CLIENT_ID')
        self.client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        self.sotd_channel_id = int(os.getenv('SOTD_CHANNEL_ID')) if os.getenv('SOTD_CHANNEL_ID') else None
        
        # Initialize Spotify client
        if self.client_id and self.client_secret:
            auth_manager = SpotifyClientCredentials(client_id=self.client_id, client_secret=self.client_secret)
            self.spotify = spotipy.Spotify(auth_manager=auth_manager)
        else:
            self.spotify = None
            print("Warning: Spotify credentials not found. SOTD functionality will be limited.")

    @commands.Cog.listener()
    async def on_ready(self):
        """Start the scheduled task when the cog is ready"""
        if not self.daily_sotd_task.is_running():
            self.daily_sotd_task.start()
            print("SOTD daily task started")

    @app_commands.command(name="sotd", description="Add a song to the Song of the Day library")
    async def add_song(self, interaction: discord.Interaction, spotify_url: str):
        """Add a song to the SOTD database"""
        await interaction.response.defer(ephemeral=True)
        
        if not self.spotify:
            await interaction.followup.send("❌ Spotify API is not configured. Please check your environment variables.")
            return
        
        # Extract track ID from Spotify URL
        try:
            track_id = self.extract_track_id(spotify_url)
            if not track_id:
                embed = discord.Embed(
                    title="❌ Invalid Spotify URL",
                    description="Please provide a valid Spotify track URL.",
                    color=0xE74C3C  # Red color for error
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Get track information from Spotify
            track = self.spotify.track(track_id)
            
            track_name = track['name']
            artist_name = ', '.join([artist['name'] for artist in track['artists']])
            album_cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None
            
            if not album_cover_url:
                await interaction.followup.send("❌ Could not retrieve album cover.")
                return
            
            # Check if song can be added
            can_add, reason = can_add_song(track_name, artist_name)
            if not can_add:
                embed = discord.Embed(
                    title=f"❌ {track_name} by {artist_name}",
                    description=(
                        f"This song is already in the library and hasn't been featured yet!\n"
                        f"You can add it again after it's been featured."
                    ),
                    color=0xE74C3C  # Red color for error
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Add to database
            user_id = interaction.user.id
            add_sotd_song(user_id, track_name, artist_name, album_cover_url, spotify_url)
            
            # Create embed for confirmation
            embed = discord.Embed(
                title=f"✅ {track_name} by {artist_name}",
                description=f"Added to the library",
                color=0x1DB954  # Spotify green
            )
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error adding song: {e}")
            await interaction.followup.send(f"❌ Error adding song: {str(e)}")

    def extract_track_id(self, url):
        """Extract track ID from Spotify URL"""
        try:
            # Handle different Spotify URL formats
            if '/track/' in url:
                parts = url.split('/track/')
                if len(parts) > 1:
                    track_id = parts[1].split('?')[0]  # Remove query parameters
                    return track_id
            return None
        except Exception as e:
            print(f"Error extracting track ID: {e}")
            return None

    async def fetch_song_links(self, spotify_url):
        """Fetch Apple Music and YouTube links from song.link API"""
        try:
            # Encode the Spotify URL for the API request
            api_url = f"https://api.song.link/v1-alpha.1/links"
            params = {
                'url': spotify_url,
                'songIfSingle': 'true'
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(api_url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                # Extract Apple Music and YouTube links
                links_by_platform = data.get('linksByPlatform', {})
                apple_music_url = links_by_platform.get('appleMusic', {}).get('url')
                youtube_url = links_by_platform.get('youtube', {}).get('url')
                
                return apple_music_url, youtube_url
        except Exception as e:
            print(f"Error fetching song links: {e}")
            return None, None

    @tasks.loop(hours=24)
    async def daily_sotd_task(self):
        """Send the song of the day at midnight UTC"""
        # Check if channel is configured
        if not self.sotd_channel_id:
            print("SOTD channel not configured. Skipping daily SOTD.")
            return
        
        # Get the channel
        channel = self.bot.get_channel(self.sotd_channel_id)
        if not channel:
            print(f"Could not find SOTD channel with ID {self.sotd_channel_id}")
            return
        
        # Get a random unused song
        song = get_random_unused_song()
        if not song:
            print("No unused songs in the database.")
            return
        
        # Mark song as used
        mark_song_as_used(song['id'])
        
        # Get user who added the song
        user = self.bot.get_user(song['user_id'])
        user_mention = user.mention if user else f"User ID {song['user_id']}"
        
        # Fetch additional platform links
        apple_music_url, youtube_url = await self.fetch_song_links(song['spotify_url'])
        
        # Create embed
        embed = discord.Embed(
            title=f"{song['track_name']}",
            description=f"by {song['artist_name']}",
            color=0x1DB954  # Spotify green
        )
        embed.set_image(url=song['album_cover_url'])
        embed.add_field(name="Added by", value=user_mention, inline=False)
        
        # Build listen links field
        listen_links = [f"[Spotify]({song['spotify_url']})"]
        if apple_music_url:
            listen_links.append(f"[Apple Music]({apple_music_url})")
        if youtube_url:
            listen_links.append(f"[YouTube]({youtube_url})")
        
        embed.add_field(name="Listen", value=" | ".join(listen_links), inline=False)
        embed.set_footer(text=f"Powered by Odesli")
        
        await channel.send(embed=embed)
        print(f"Sent SOTD: {song['track_name']} by {song['artist_name']}")

    @daily_sotd_task.before_loop
    async def before_daily_sotd_task(self):
        """Wait until the bot is ready and calculate time until midnight UTC"""
        await self.bot.wait_until_ready()
        
        # Calculate time until next midnight UTC
        now = datetime.now(timezone.utc)
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_midnight - now).total_seconds()
        
        print(f"SOTD task will start in {sleep_seconds} seconds (at {next_midnight.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        await asyncio.sleep(sleep_seconds)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.daily_sotd_task.cancel()


async def setup(bot):
    await bot.add_cog(SotdCog(bot))
