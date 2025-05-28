import os
import json
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
import logging

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variable for bot token
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# File to store member usernames
MEMBERS_FILE = "members.json"

def load_members():
    """Load member usernames from JSON file"""
    try:
        with open(MEMBERS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_members(members):
    """Save member usernames to JSON file"""
    with open(MEMBERS_FILE, 'w') as f:
        json.dump(members, f, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text("Hi! I'm a bot that tags all known group members when mentioned. Send a message in the group to be included in the tag list!")

async def track_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track users who send messages in the group"""
    message = update.message
    chat = message.chat
    user = message.from_user
    
    if chat.type in ['group', 'supergroup'] and user.username and not user.is_bot:
        members = load_members()
        chat_id = str(chat.id)
        if chat_id not in members:
            members[chat_id] = []
        
        if user.username not in members[chat_id]:
            members[chat_id].append(user.username)
            save_members(members)
            logger.info(f"Added @{user.username} to members list for chat {chat_id}")

async def tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages where the bot is tagged"""
    message = update.message
    chat = message.chat
    
    # Check if the message is in a group/supergroup and contains the bot's mention
    if chat.type in ['group', 'supergroup'] and message.text:
        bot_username = context.bot.username
        if bot_username.lower() in message.text.lower():
            try:
                # Load known members from file
                members = load_members()
                chat_id = str(chat.id)
                tagged_members = [f"@{username}" for username in members.get(chat_id, []) if username != bot_username]
                
                # Fallback: If no members are stored, tag admins
                if not tagged_members:
                    admins = await context.bot.get_chat_administrators(chat.id)
                    tagged_members = [f"@{admin.user.username}" for admin in admins if not admin.user.is_bot and admin.user.username and admin.user.username != bot_username]
                    if not tagged_members:
                        await message.reply_text(
                            "No members or admins with usernames found to tag! Users must send a message to be included.",
                            reply_to_message_id=message.message_id,
                            message_thread_id=message.message_thread_id if message.is_topic_message else None
                        )
                        return
                
                # Format tags with one per line
                tagged_message = "\n".join(tagged_members)
                
                # Telegram has a 4096-character limit for messages
                max_length = 4000
                if len(tagged_message) > max_length:
                    # Split into multiple messages if too long
                    parts = []
                    current_part = ""
                    for tag in tagged_members:
                        if len(current_part) + len(tag) + 1 <= max_length:
                            current_part += tag + "\n"
                        else:
                            parts.append(current_part.rstrip())
                            current_part = tag + "\n"
                    if current_part:
                        parts.append(current_part.rstrip())
                    
                    for part in parts:
                        await message.reply_text(
                            part,
                            reply_to_message_id=message.message_id,
                            message_thread_id=message.message_thread_id if message.is_topic_message else None
                        )
                        # Avoid rate limiting
                        await asyncio.sleep(1)
                else:
                    await message.reply_text(
                        tagged_message,
                        reply_to_message_id=message.message_id,
                        message_thread_id=message.message_thread_id if message.is_topic_message else None
                    )
                
                logger.info(f"Tagged {len(tagged_members)} members in chat {chat.id}")
            except TelegramError as e:
                logger.error(f"Error tagging members: {e}")
                await message.reply_text(
                    "Sorry, I couldn't tag everyone. Please ensure I'm an admin and try again.",
                    reply_to_message_id=message.message_id,
                    message_thread_id=message.message_thread_id if message.is_topic_message else None
                )
        else:
            # Track members even if the bot isn't tagged
            await track_members(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Run the bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tag_all))
    application.add_error_handler(error_handler)
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()