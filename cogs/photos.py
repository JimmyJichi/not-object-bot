import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import shutil
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from geopy.geocoders import Nominatim
from utils.database import get_user_coins, spend_coins


class PhotosCog(commands.Cog):
    """Cog for handling photo-related commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.photos_dir = "photos"
        self.revealed_dir = os.path.join(self.photos_dir, "revealed")

    def get_photo_counts(self):
        """Get counts of total photos and revealed photos"""
        try:
            # Get all image files from main photos directory (unrevealed)
            unrevealed_files = [f for f in os.listdir(self.photos_dir) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
            
            # Get all image files from revealed directory
            revealed_files = [f for f in os.listdir(self.revealed_dir) 
                             if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
            
            # Total photos = unrevealed + revealed
            total_photos = len(unrevealed_files) + len(revealed_files)
            revealed_photos = len(revealed_files)
            
            return total_photos, revealed_photos
        except Exception as e:
            print(f"Error getting photo counts: {e}")
            return 0, 0

    def get_exif_data(self, image_path):
        """Extract EXIF data from an image"""
        try:
            image = Image.open(image_path)
            exif_data = image._getexif()
            
            if exif_data is not None:
                exif = {}
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    exif[tag] = value
                return exif
        except Exception as e:
            print(f"Error reading EXIF data: {e}")
        return {}

    def get_gps_data(self, exif_data):
        """Extract GPS data from EXIF"""
        if 'GPSInfo' not in exif_data:
            return None
        
        gps_info = exif_data['GPSInfo']
        gps_data = {}
        
        for key, value in gps_info.items():
            tag = GPSTAGS.get(key, key)
            gps_data[tag] = value
        
        return gps_data

    def convert_to_degrees(self, value):
        """Convert GPS coordinates to degrees"""
        d, m, s = value
        return d + (m / 60.0) + (s / 3600.0)

    def get_location_from_gps(self, gps_data):
        """Get city and country from GPS coordinates using reverse geocoding"""
        if not gps_data:
            return None, None
        
        try:
            lat = self.convert_to_degrees(gps_data['GPSLatitude'])
            lon = self.convert_to_degrees(gps_data['GPSLongitude'])
            
            if gps_data['GPSLatitudeRef'] == 'S':
                lat = -lat
            if gps_data['GPSLongitudeRef'] == 'W':
                lon = -lon
            
            # Use Nominatim for reverse geocoding
            geolocator = Nominatim(user_agent="not-object-bot")
            location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True)
            
            if location:
                address = location.raw.get('address', {})
                city = address.get('city') or address.get('town') or address.get('village') or address.get('hamlet')
                country = address.get('country')
                
                if city and country:
                    return city, country
                elif country:
                    return f"{lat:.4f}°N" if lat >= 0 else f"{abs(lat):.4f}°S", country
                else:
                    return f"{lat:.4f}°N" if lat >= 0 else f"{abs(lat):.4f}°S", f"{lon:.4f}°E" if lon >= 0 else f"{abs(lon):.4f}°W"
            else:
                # Fallback to coordinates if geocoding fails
                return f"{lat:.4f}°N" if lat >= 0 else f"{abs(lat):.4f}°S", f"{lon:.4f}°E" if lon >= 0 else f"{abs(lon):.4f}°W"
                
        except Exception as e:
            print(f"Error processing GPS data: {e}")
            return None, None

    def get_random_photo_info(self):
        """Get a random photo from the photos directory with location info and move it to revealed"""
        try:
            # Get all image files from photos directory
            image_files = [f for f in os.listdir(self.photos_dir) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
            
            if not image_files:
                return None, "You have seen all the photos. Stay tuned for more!"
            
            # Select a random photo
            random_photo = random.choice(image_files)
            photo_path = os.path.join(self.photos_dir, random_photo)
            
            # Extract EXIF data before moving the file
            exif_data = self.get_exif_data(photo_path)
            gps_data = self.get_gps_data(exif_data)
            
            # Get location information
            city, country = self.get_location_from_gps(gps_data)
            
            # Format location string
            location_info = ""
            if city and country:
                location_info = f"📍 **Location:** {city}, {country}"
            # elif exif_data.get('DateTime'):
            #     location_info = f"📅 **Date:** {exif_data['DateTime']}"
            else:
                location_info = "📍 **Location:** Unknown"
            
            # Move the photo to revealed directory
            revealed_path = os.path.join(self.revealed_dir, random_photo)
            shutil.move(photo_path, revealed_path)
            
            return revealed_path, location_info
            
        except Exception as e:
            print(f"Error getting random photo: {e}")
            return None, f"Error accessing photos: {str(e)}"

    @app_commands.command(name='photo', description='Spend 500 coins to get a random photo from Object\'s phone!')
    async def random_photo(self, interaction: discord.Interaction):
        """Command to get a random photo for 500 coins"""
        # Check if user is in the correct channel
        photo_channel_id = os.getenv('PHOTO_CHANNEL')        
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        # Check if user has enough coins
        current_coins = get_user_coins(user_id)
        required_coins = 500
        
        if current_coins < required_coins:
            embed = discord.Embed(
                title="💰 Insufficient Coins",
                description=f"You need **{required_coins} coins** to get a photo!\n\nYour current balance: **{current_coins} coins**",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if photo_channel_id and str(interaction.channel_id) != photo_channel_id:
            embed = discord.Embed(
                title="🚫 Wrong Channel",
                description=f"This command can only be used in <#{photo_channel_id}>!",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Spend the coins
        if not spend_coins(user_id, username, required_coins):
            embed = discord.Embed(
                title="❌ Transaction Failed",
                description="Unable to process the transaction. Please try again.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get random photo
        photo_path, location_info = self.get_random_photo_info()
        
        if photo_path is None:
            # Refund the coins if photo retrieval failed
            from utils.database import add_coins
            add_coins(user_id, username, required_coins)
            
            embed = discord.Embed(
                title="❌ Photo Unavailable",
                description=location_info,
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get photo counts
        total_photos, revealed_photos = self.get_photo_counts()

        # Get the user to mention
        photo_mention_user_id = os.getenv('PHOTO_MENTION_USER')
        mention_text = f"<@{photo_mention_user_id}>" if photo_mention_user_id else "Object"
        
        # Create embed with photo info
        embed = discord.Embed(
            title="📸 Random Photo",
            description=f"Here's a random photo from {mention_text}'s phone!\n\n{location_info}\n\n💰 **Cost:** {required_coins} coins\n💳 **Balance:** {current_coins - required_coins} coins",
            color=0x4ecdc4
        )
        
        # Send the photo embedded in the message
        try:
            with open(photo_path, 'rb') as f:
                photo_file = discord.File(f, filename=os.path.basename(photo_path))
                embed.set_image(url=f"attachment://{os.path.basename(photo_path)}")
                await interaction.response.send_message(embed=embed, file=photo_file)
        except Exception as e:
            # Refund the coins if file sending failed
            from utils.database import add_coins
            add_coins(user_id, username, required_coins)
            
            embed = discord.Embed(
                title="❌ Error Sending Photo",
                description=f"Failed to send the photo: {str(e)}",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(PhotosCog(bot))
