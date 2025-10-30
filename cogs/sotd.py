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
        
        # Extract Spotify resource type and ID from URL
        try:
            resource = self.extract_spotify_resource(spotify_url)
            if not resource:
                embed = discord.Embed(
                    title="❌ Invalid Spotify URL",
                    description="Please provide a valid Spotify track, album, or playlist URL.",
                    color=0xE74C3C
                )
                await interaction.followup.send(embed=embed)
                return

            resource_type, resource_id = resource

            user_id = interaction.user.id

            if resource_type == 'track':
                # Get track information from Spotify
                track = self.spotify.track(resource_id)

                track_name = track['name']
                artist_name = ', '.join([artist['name'] for artist in track['artists']])
                album_cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None

                if not album_cover_url:
                    await interaction.followup.send("❌ Could not retrieve album cover.")
                    return

                # Check if song can be added
                can_add, _ = can_add_song(track_name, artist_name)
                if not can_add:
                    embed = discord.Embed(
                        title=f"❌ {track_name} by {artist_name}",
                        description=(
                            f"This song is already in the library and hasn't been featured yet!\n"
                            f"You can add it again after it's been featured."
                        ),
                        color=0xE74C3C
                    )
                    await interaction.followup.send(embed=embed)
                    return

                # Add to database
                add_sotd_song(user_id, track_name, artist_name, album_cover_url, spotify_url)

                # Create embed for confirmation (track path retains current behavior)
                embed = discord.Embed(
                    title=f"✅ {track_name} by {artist_name}",
                    description=f"Added to the library",
                    color=0x1DB954
                )
                await interaction.followup.send(embed=embed)

            elif resource_type == 'album':
                # Fetch album and tracks (with pagination)
                album = self.spotify.album(resource_id)
                album_name = album.get('name') or 'Album'
                album_cover_url = album['images'][0]['url'] if album.get('images') else None

                added_count = 0
                limit = 50
                offset = 0
                while True:
                    tracks_page = self.spotify.album_tracks(resource_id, limit=limit, offset=offset)
                    items = tracks_page.get('items', [])
                    if not items:
                        break
                    for item in items:
                        track_name = item['name']
                        artist_name = ', '.join([artist['name'] for artist in item['artists']])
                        track_id = item.get('id')
                        if not track_id:
                            continue
                        track_url = f"https://open.spotify.com/track/{track_id}"
                        cover_url = album_cover_url
                        if not cover_url:
                            # Fallback: fetch full track to get album image if album image missing
                            track_full = self.spotify.track(track_id)
                            cover_url = track_full['album']['images'][0]['url'] if track_full['album'].get('images') else None
                        if not cover_url:
                            continue
                        can_add, _ = can_add_song(track_name, artist_name)
                        if can_add:
                            add_sotd_song(user_id, track_name, artist_name, cover_url, track_url)
                            added_count += 1
                    if tracks_page.get('next'):
                        offset += limit
                    else:
                        break

                embed = discord.Embed(
                    title=f"✅ {album_name}",
                    description=f"{added_count} tracks added",
                    color=0x1DB954
                )
                await interaction.followup.send(embed=embed)

            elif resource_type == 'playlist':
                # Fetch playlist tracks (with pagination)
                playlist = self.spotify.playlist(resource_id)
                playlist_name = (playlist.get('name') or 'Playlist') if isinstance(playlist, dict) else 'Playlist'
                added_count = 0
                limit = 100
                offset = 0
                while True:
                    page = self.spotify.playlist_items(resource_id, limit=limit, offset=offset)
                    items = page.get('items', [])
                    if not items:
                        break
                    for item in items:
                        track = item.get('track')
                        if not track:
                            continue
                        # Skip local or unavailable tracks
                        track_id = track.get('id')
                        if not track_id:
                            continue
                        track_name = track.get('name')
                        artist_name = ', '.join([artist['name'] for artist in track.get('artists', [])])
                        track_url = f"https://open.spotify.com/track/{track_id}"
                        album_images = (track.get('album') or {}).get('images') or []
                        cover_url = album_images[0]['url'] if album_images else None
                        if not cover_url:
                            # Fallback fetch if needed
                            track_full = self.spotify.track(track_id)
                            cover_url = track_full['album']['images'][0]['url'] if track_full['album'].get('images') else None
                        if not cover_url:
                            continue
                        can_add, _ = can_add_song(track_name, artist_name)
                        if can_add:
                            add_sotd_song(user_id, track_name, artist_name, cover_url, track_url)
                            added_count += 1
                    if page.get('next'):
                        offset += limit
                    else:
                        break

                embed = discord.Embed(
                    title=f"✅ {playlist_name}",
                    description=f"{added_count} tracks added",
                    color=0x1DB954
                )
                await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Unsupported Spotify URL",
                    description="Please provide a Spotify track, album, or playlist URL.",
                    color=0xE74C3C
                )
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error adding song: {e}")
            await interaction.followup.send(f"❌ Error adding song: {str(e)}")

    def extract_spotify_resource(self, url):
        """Extract Spotify resource type and ID from URL. Returns tuple (type, id) or None"""
        try:
            # Normalize URL by stripping query params and fragments
            base = url.split('?')[0].split('#')[0]
            if '/track/' in base:
                track_id = base.split('/track/')[1].split('/')[0]
                return ('track', track_id)
            if '/album/' in base:
                album_id = base.split('/album/')[1].split('/')[0]
                return ('album', album_id)
            if '/playlist/' in base:
                playlist_id = base.split('/playlist/')[1].split('/')[0]
                return ('playlist', playlist_id)
            return None
        except Exception as e:
            print(f"Error extracting Spotify resource: {e}")
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
