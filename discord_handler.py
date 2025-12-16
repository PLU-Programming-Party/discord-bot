"""
Discord bot interactions and message handling
"""
import discord
import logging
from discord.ext import commands
from claude_handler import gather_requirements, get_file_changes
from context_loader import load_website_context
from github_handler import apply_changes, push_to_github

logger = logging.getLogger(__name__)

# Store ongoing conversations by user ID
user_conversations = {}

class ConversationState:
    def __init__(self, user_id, initial_prompt):
        self.user_id = user_id
        self.initial_prompt = initial_prompt
        self.conversation_history = []
        self.requirements = None
        self.phase = "gathering"  # "gathering" or "implementing"
    
    def add_message(self, role, content):
        """Add a message to the conversation history"""
        self.conversation_history.append({"role": role, "content": content})
    
    def get_full_context(self):
        """Get the full conversation for Claude"""
        return self.conversation_history

async def process_suggestion(message: discord.Message):
    """
    Process a user's website modification suggestion
    Phase 1: Gather requirements (ask clarifying questions)
    Phase 2: Implement changes (once requirements are clear)
    """
    user_id = message.author.id
    user_prompt = message.content
    # HAL 9000 Easter egg for users with "dav" in their name
    if "dav" in message.author.name.lower():
        await message.reply("I'm sorry dav, but I can't do that.")
        return

    
    # Initialize or retrieve conversation
    if user_id not in user_conversations:
        user_conversations[user_id] = ConversationState(user_id, user_prompt)
        logger.info(f"Processing prompt from {message.author.name}: {user_prompt}")
    else:
        # User is responding to questions
        logger.info(f"User {message.author.name} responding: {user_prompt}")
        user_conversations[user_id].add_message("user", user_prompt)
    
    # Load website context
    website_context = load_website_context()
    if not website_context:
        await message.reply("I couldn't load the website context. Please try again later.")
        return
    
    state = user_conversations[user_id]
    
    # PHASE 1: Gather Requirements
    if state.phase == "gathering":
        logger.info("Phase: Gathering Requirements")
        
        requirements = await gather_requirements(
            state.initial_prompt,
            website_context,
            state.conversation_history if state.conversation_history else None
        )
        
        if requirements.get("questions"):
            # Ask the questions
            questions_text = "\n".join([f"• {q}" for q in requirements["questions"]])
            response = f"I have some questions to better understand your request:\n\n{questions_text}"
            await message.reply(response)
            
            # Add Claude's questions to history
            state.add_message("assistant", f"Questions: {requirements['questions']}")
            state.requirements = requirements
            
        elif requirements.get("ready_to_implement"):
            # Ready to proceed
            logger.info(f"Ready to implement: {requirements.get('summary')}")
            state.phase = "implementing"
            await message.reply("Got it! I understand the requirements. Now generating the changes...")
            
            # Proceed to implementation
            await implement_changes(message, state, website_context)
        else:
            await message.reply("I need clarification. Could you provide more specific details about your request?")
    
    # PHASE 2: Implement Changes
    elif state.phase == "implementing":
        # Re-check if we now have enough info
        requirements = await gather_requirements(
            state.initial_prompt,
            website_context,
            state.conversation_history
        )
        
        if requirements.get("ready_to_implement"):
            logger.info("Implementing after clarifications")
            await implement_changes(message, state, website_context)
        else:
            # Still need more info
            questions_text = "\n".join([f"• {q}" for q in requirements["questions"]])
            response = f"I still have some questions:\n\n{questions_text}"
            await message.reply(response)
            state.requirements = requirements

async def implement_changes(message: discord.Message, state: ConversationState, website_context: str):
    """Generate and apply the file changes"""
    try:
        # Full prompt with conversation context
        full_prompt = state.initial_prompt
        if state.conversation_history:
            clarifications = "\n".join([
                msg["content"] for msg in state.conversation_history if msg["role"] == "user"
            ])
            full_prompt = f"{state.initial_prompt}\n\nClarifications provided:\n{clarifications}"
        
        logger.info("Generating file changes...")
        await message.reply("⏳ Generating changes...")
        
        # Get file changes from Claude
        file_changes = await get_file_changes(full_prompt, website_context)
        
        if not file_changes:
            await message.reply("❌ Failed to generate changes. Please try again.")
            return
        
        num_files = len(file_changes.get("files", []))
        logger.info(f"Generated changes for {num_files} files")
        
        # Apply changes to repository
        await message.reply(f"📝 Applying {num_files} file changes...")
        success = apply_changes(file_changes)
        
        if not success:
            await message.reply("❌ Failed to apply changes to the repository.")
            return
        
        # Push to GitHub
        await message.reply("🚀 Pushing to GitHub...")
        push_success = push_to_github()
        
        if push_success:
            changed_files = [f["path"] for f in file_changes.get("files", [])]
            files_list = "\n".join([f"✅ {f}" for f in changed_files])
            confirmation = f"""✨ Changes deployed successfully!

Modified files:
{files_list}

The website will update in a few moments..."""
            await message.reply(confirmation)
            logger.info(f"Successfully deployed changes")
            
            # Clean up conversation
            if state.user_id in user_conversations:
                del user_conversations[state.user_id]
        else:
            await message.reply("⚠️ Changes applied but failed to push to GitHub. Please check the repository.")
    
    except Exception as e:
        logger.error(f"Error implementing changes: {e}")
        await message.reply(f"❌ An error occurred: {str(e)}")
