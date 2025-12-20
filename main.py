"""
Main entry point for Discord Bot Website Assistant & Webwritten API

For Railway deployment:
- Flask serves on PORT (exposed to internet)
- Discord bot runs in background thread
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

def daily_tasks():
    """Run daily winner selection and pool maintenance"""
    logger.info("Running daily Webwritten tasks...")
    try:
        winner = select_daily_winner()
        if winner:
            logger.info(f"Daily winner selected: {winner['sentence'][:50]}...")
        else:
            logger.info("No winner today (not enough votes)")
        maintain_sentence_pool()
    except Exception as e:
        logger.error(f"Error in daily tasks: {e}")

def setup_scheduler():
    """Set up the daily scheduler"""
    global scheduler
    scheduler = BackgroundScheduler()
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
    if message.author == bot.user:
        return
    channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
    if message.channel.id != channel_id:
        return
    await setup_discord_handler(bot, message)

def run_discord_bot():
    """Run Discord bot in a separate thread"""
    try:
        init_repo()
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            logger.error("DISCORD_TOKEN not found")
            return
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.start(token))
    except Exception as e:
        logger.error(f"Error in Discord bot: {e}")

# Health check endpoint
@flask_app.route("/health")
def health():
    return {"status": "ok", "service": "webwritten-api"}

@flask_app.route("/")
def root():
    return {"status": "ok", "message": "Webwritten API is running", "endpoints": ["/api/webwritten/story", "/api/webwritten/vote", "/api/webwritten/submit", "/api/webwritten/stats"]}

if __name__ == "__main__":
    logger.info("Starting services...")
    
    # Seed initial content
    seed_initial_content()
    
    # Start scheduler
    setup_scheduler()
    
    # Start Discord bot in background thread
    discord_thread = threading.Thread(target=run_discord_bot, daemon=True)
    discord_thread.start()
    logger.info("Discord bot thread started")
    
    # Run Flask (main thread - this is what Railway exposes)
    port = int(os.getenv("PORT", 5000))
    logger.info(f"Starting Flask API on port {port}")
    flask_app.run(host="0.0.0.0", port=port, threaded=True)
