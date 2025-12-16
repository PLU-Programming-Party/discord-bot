"""
Discord event handler - processes messages from #website-prompts
"""
import discord
import logging
from claude_handler import get_file_changes
from github_handler import apply_changes_and_commit
from context_loader import get_website_context

logger = logging.getLogger(__name__)

async def setup_discord_handler(bot, message):
    """
    Handle incoming Discord messages and orchestrate the workflow
    """
    try:
        prompt = message.content.strip()
        
        if not prompt:
            return
        
        # Check for rocket emoji - required to execute commands
        if "🚀" not in prompt:
            await message.reply(
                "⚠️ **Rocket emoji required!** 🚀\n\n"
                "To make changes to the website, please include a 🚀 emoji in your request.\n\n"
                "Example: `🚀 make the title bigger and red text`"
            )
            return
        
        # Send initial acknowledgment
        await message.add_reaction("⏳")
        
        logger.info(f"Processing prompt: {prompt}")
        
        # Get website context
        context = get_website_context()
        
        # Get Claude's suggestions
        embed = discord.Embed(
            title="🤖 Analyzing your request...",
            description="Claude is reviewing your suggestion. This may take a moment.",
            color=discord.Color.blue()
        )
        status_msg = await message.reply(embed=embed)
        
        # Call Claude
        file_changes = await get_file_changes(prompt, context)
        
        if not file_changes:
            await status_msg.edit(
                embed=discord.Embed(
                    title="❌ No changes generated",
                    description="Claude couldn't generate changes for your request.",
                    color=discord.Color.red()
                )
            )
            return
        
        # Apply changes to repo
        embed = discord.Embed(
            title="📝 Applying changes...",
            description="Writing changes to the website repository.",
            color=discord.Color.blue()
        )
        await status_msg.edit(embed=embed)
        
        commit_hash = apply_changes_and_commit(file_changes, prompt)
        
        # Success response
        embed = discord.Embed(
            title="✅ Changes deployed!",
            description=f"Your suggestion has been applied to the website.\n\n**Commit**: `{commit_hash[:7]}`\n\nThe website will update in 2-3 minutes as GitHub Actions rebuilds and deploys.",
            color=discord.Color.green()
        )
        embed.add_field(name="Your request", value=prompt, inline=False)
        files_count = len(file_changes.get("files", []))
        embed.add_field(name="Files changed", value=f"{files_count} file(s)", inline=False)
        
        await status_msg.edit(embed=embed)
        
        # Remove loading reaction
        await message.remove_reaction("⏳", bot.user)
        
        # Add success reaction
        await message.add_reaction("✅")
        
        logger.info(f"Successfully deployed changes. Commit: {commit_hash}")
        
    except Exception as e:
        logger.error(f"Error processing prompt: {e}")
        
        embed = discord.Embed(
            title="❌ Error",
            description=f"Something went wrong: {str(e)}",
            color=discord.Color.red()
        )
        await message.reply(embed=embed)
        await message.add_reaction("❌")
