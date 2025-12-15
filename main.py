"""
Main entry point for Discord Bot Website Assistant
"""
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Import handlers
from discord_handler import setup_discord_handler
from github_handler import init_repo

@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user}")
    logger.info("Ready to process website suggestions!")

@bot.event
async def on_message(message):
    # Don't respond to own messages
    if message.author == bot.user:
        return
    
    # Only process in the designated channel
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID"))
    if message.channel.id != channel_id:
        return
    
    # Process the prompt
    await setup_discord_handler(bot, message)

async def main():
    """Start the bot"""
    try:
        # Initialize repo
        init_repo()
        
        # Start bot
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN not found in .env")
        
        await bot.start(token)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
