"""
Main entry point for Discord Bot Website Assistant & Webwritten API
"""
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import threading
import asyncio

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

# Flask and Webwritten
from webwritten_api import app as flask_app, seed_initial_content, select_daily_winner, maintain_sentence_pool

# Scheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Global scheduler
scheduler = None

def run_flask():
    """Run Flask in a separate thread"""
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting Flask API on port {port}")
    flask_app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)

def daily_tasks():
    """Run daily winner selection and pool maintenance"""
    logger.info("Running daily Webwritten tasks...")
    try:
        # Select winner
        winner = select_daily_winner()
        if winner:
            logger.info(f"Daily winner selected: {winner['sentence'][:50]}...")
        else:
            logger.info("No winner today (not enough votes)")
        
        # Maintain sentence pool
        maintain_sentence_pool()
        
    except Exception as e:
        logger.error(f"Error in daily tasks: {e}")

def setup_scheduler():
    """Set up the daily scheduler"""
    global scheduler
    scheduler = BackgroundScheduler()
    
    # Run daily at midnight UTC
    scheduler.add_job(
        daily_tasks,
        CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="daily_webwritten",
        name="Daily Webwritten Winner Selection",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started - daily tasks at midnight UTC")

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
    """Start the bot and API"""
    try:
        # Initialize repo
        init_repo()
        
        # Seed initial Webwritten content
        logger.info("Seeding Webwritten content...")
        seed_initial_content()
        
        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Set up scheduler
        setup_scheduler()
        
        # Start bot
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN not found in .env")
        
        await bot.start(token)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        if scheduler:
            scheduler.shutdown()
        raise

if __name__ == "__main__":
    asyncio.run(main())
