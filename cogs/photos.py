import discord
from discord import app_commands
from discord.ext import commands
import os
import random
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from geopy.geocoders import Nominatim
from utils.database import get_user_coins, spend_coins


class PhotosCog(commands.Cog):
    """Cog for handling photo-related commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.photos_dir = "photos"

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
        """Get a random photo from the photos directory with location info"""
        try:
            # Get all image files from photos directory
            image_files = [f for f in os.listdir(self.photos_dir) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
            
            if not image_files:
                return None, "No photos found in the photos directory!"
            
            # Select a random photo
            random_photo = random.choice(image_files)
            photo_path = os.path.join(self.photos_dir, random_photo)
            
            # Extract EXIF data
            exif_data = self.get_exif_data(photo_path)
            gps_data = self.get_gps_data(exif_data)
            
            # Get location information
            city, country = self.get_location_from_gps(gps_data)
            
            # Format location string
            location_info = ""
            if city and country:
                location_info = f"📍 **Location:** {city}, {country}"
            elif exif_data.get('DateTime'):
                location_info = f"📅 **Date:** {exif_data['DateTime']}"
            else:
                location_info = "📍 **Location:** Unknown"
            
            return photo_path, location_info
            
        except Exception as e:
            print(f"Error getting random photo: {e}")
            return None, f"Error accessing photos: {str(e)}"

    @app_commands.command(name='photo', description='Spend 1000 coins to get a random photo from Object\'s phone!')
    async def random_photo(self, interaction: discord.Interaction):
        """Command to get a random photo for 1000 coins"""
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        # Check if user has enough coins
        current_coins = get_user_coins(user_id)
        required_coins = 1000
        
        if current_coins < required_coins:
            embed = discord.Embed(
                title="💰 Insufficient Coins",
                description=f"You need **{required_coins} coins** to get a random photo!\n\nYour current balance: **{current_coins} coins**",
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
        
        # Create embed with photo info
        embed = discord.Embed(
            title="📸 Random Photo",
            description=f"Here's a random photo from Object's phone!\n\n{location_info}\n\n💰 **Cost:** {required_coins} coins\n💳 **Remaining balance:** {current_coins - required_coins} coins",
            color=0x4ecdc4
        )
        
        # Send the photo as a file attachment
        try:
            with open(photo_path, 'rb') as f:
                photo_file = discord.File(f, filename=os.path.basename(photo_path))
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
