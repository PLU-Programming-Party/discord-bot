"""
Discord bot interactions and message handling - Agent-based approach
"""
import discord
import logging
import os
from discord.ext import commands
from claude_handler import AgentSession
from github_handler import push_changes

logger = logging.getLogger(__name__)

# Store ongoing agent sessions by user ID
user_sessions = {}

# Repository path
REPO_PATH = "./website_repo"

async def process_suggestion(message: discord.Message):
    """
    Process a user's website modification suggestion using the agent approach
    """
    user_id = message.author.id
    user_prompt = message.content
    
    # HAL 9000 Easter egg for users with "dav" in their name
    if "dav" in message.author.name.lower():
        await message.reply("I'm sorry dav, but I can't do that.")
        return
    
    # Check if user has an existing session waiting for a response
    if user_id in user_sessions:
        session = user_sessions[user_id]
        if session.pending_question:
            # User is responding to a question
            logger.info(f"User {message.author.name} responding to question: {user_prompt}")
            session.add_user_response(user_prompt)
            await message.reply("⏳ Got it, continuing with your request...")
            
            # Continue the agent loop
            status, result = await session.run_agent_loop()
            await handle_agent_result(message, session, status, result)
            return
    
    # New request - create a new session
    logger.info(f"New request from {message.author.name}: {user_prompt}")
    
    # Check repo exists
    if not os.path.exists(REPO_PATH):
        await message.reply("❌ Website repository not found. Please try again later.")
        return
    
    # Create agent session
    session = AgentSession(REPO_PATH)
    user_sessions[user_id] = session
    
    await message.reply("🤖 Working on your request... I'll explore the codebase and make the changes.")
    
    # Run the agent
    status, result = await session.run_agent_loop(user_prompt)
    await handle_agent_result(message, session, status, result)


async def handle_agent_result(message: discord.Message, session: AgentSession, status: str, result: str):
    """Handle the result from the agent loop"""
    user_id = message.author.id
    
    if status == "question":
        # Agent needs clarification
        await message.reply(f"❓ {result}")
        # Keep session alive for response
        
    elif status == "complete":
        # Agent finished - commit and push changes
        if session.files_changed:
            logger.info(f"Agent completed. Files changed: {session.files_changed}")
            await message.reply(f"📝 Changes made to {len(session.files_changed)} files. Pushing to GitHub...")
            
            try:
                # Commit and push
                commit_message = f"Bot: {message.content[:50]}..." if len(message.content) > 50 else f"Bot: {message.content}"
                success = push_changes(REPO_PATH, session.files_changed, commit_message)
                
                if success:
                    files_list = "\n".join([f"✅ {f}" for f in session.files_changed])
                    await message.reply(f"""✨ Changes deployed successfully!

Modified files:
{files_list}

{result}

The website will update in a few moments...""")
                else:
                    await message.reply("⚠️ Changes were made locally but failed to push to GitHub.")
                    
            except Exception as e:
                logger.error(f"Error pushing changes: {e}")
                await message.reply(f"⚠️ Changes made but error pushing: {str(e)}")
        else:
            await message.reply(f"ℹ️ {result}")
        
        # Clean up session
        if user_id in user_sessions:
            del user_sessions[user_id]
            
    elif status == "error":
        await message.reply(f"❌ Error: {result}")
        # Clean up session
        if user_id in user_sessions:
            del user_sessions[user_id]


async def setup_discord_handler(bot, message: discord.Message):
    """
    Main entry point for processing Discord messages
    Called from main.py when a message is received in the designated channel
    """
    await process_suggestion(message)
