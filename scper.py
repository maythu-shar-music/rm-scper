import re
import os
import asyncio
import logging
import aiofiles
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client, filters
from pyrogram.errors import (
    UserAlreadyParticipant,
    InviteHashExpired,
    InviteHashInvalid,
    PeerIdInvalid,
    InviteRequestSent,
    ChatAdminRequired,
    FloodWait,
    ChannelInvalid,
    ChannelPrivate,
    UsernameInvalid,
    UsernameNotOccupied
)
from urllib.parse import urlparse
from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    ADMIN_LIMIT,
    ADMIN_IDS,
    DEFAULT_LIMIT
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize clients
app = Client(
    "app_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=200
)

user = Client(
    "user_session",
    session_string=SESSION_STRING,
    workers=200
)

START_MESSAGE = """
<b>Welcome to the Credit Card Scraper Bot 🕵️‍♂️💳</b>

I'm here to help you scrape credit card information from Telegram channels.
Use the commands below to get started:

<code>/scr [channel_username] [limit]</code> - Scrape from a single channel
<code>/mc [channel1] [channel2] ... [limit]</code> - Scrape from multiple channels

<b>Optional Filters:</b>
• Add BIN number to filter by card BIN
• Add bank name to filter by bank

<b>Examples:</b>
<code>/scr @channel 100</code>
<code>/scr @channel 100 485898</code> (BIN filter)
<code>/scr @channel 100 Chase</code> (Bank filter)
"""

# Compile regex patterns
CC_PATTERN = re.compile(r'\b\d{15,16}\D*\d{2}\D*\d{2,4}\D*\d{3,4}\b')
NUMBER_PATTERN = re.compile(r'\d+')

async def safe_get_chat(client, identifier):
    """Safely get chat information with proper error handling"""
    try:
        if isinstance(identifier, str) and identifier.startswith("https://t.me/+"):
            # Handle private invite links
            return await client.get_chat(identifier)
        elif isinstance(identifier, str) and identifier.lstrip("-").isdigit():
            # Handle numeric chat IDs
            return await client.get_chat(int(identifier))
        else:
            # Handle usernames
            return await client.get_chat(identifier)
    except (PeerIdInvalid, ChannelInvalid, ChannelPrivate, UsernameInvalid, UsernameNotOccupied) as e:
        logger.error(f"Failed to get chat {identifier}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting chat {identifier}: {e}")
        return None

async def scrape_messages(client, chat_id, limit, start_number=None, bank_name=None):
    messages = []
    count = 0
    
    try:
        # First, verify we can access the chat
        chat = await safe_get_chat(client, chat_id)
        if not chat:
            logger.error(f"Cannot access chat: {chat_id}")
            return messages
            
        logger.info(f"Starting to scrape messages from {chat.title} with limit {limit}")
        
        async for message in client.search_messages(chat_id, limit=limit*5):  # Search more messages to find enough cards
            if count >= limit:
                break
                
            text = message.text or message.caption
            if not text:
                continue
                
            # Apply bank name filter
            if bank_name and bank_name.lower() not in text.lower():
                continue
                
            # Find CC matches
            matches = CC_PATTERN.findall(text)
            for match in matches:
                if count >= limit:
                    break
                    
                # Extract numbers
                numbers = NUMBER_PATTERN.findall(match)
                if len(numbers) == 4:
                    card_number, month, year, cvv = numbers
                    
                    # Format year to 2 digits
                    if len(year) == 4:
                        year = year[-2:]
                    elif len(year) == 2:
                        pass  # Already 2 digits
                    else:
                        continue  # Invalid year format
                        
                    # Validate month
                    if not (1 <= int(month) <= 12):
                        continue
                        
                    # Apply BIN filter
                    if start_number and not card_number.startswith(start_number[:6]):
                        continue
                        
                    # Format and add to results
                    formatted = f"{card_number}|{month}|{year}|{cvv}"
                    if len(card_number) in [15, 16] and len(cvv) in [3, 4]:
                        messages.append(formatted)
                        count += 1
                        
    except Exception as e:
        logger.error(f"Error scraping messages from {chat_id}: {e}")
        
    return messages

def remove_duplicates(messages):
    unique_messages = list(set(messages))
    duplicates_removed = len(messages) - len(unique_messages)
    logger.info(f"Removed {duplicates_removed} duplicates")
    return unique_messages, duplicates_removed

async def send_results(client, message, unique_messages, duplicates_removed, source_name, bin_filter=None, bank_filter=None):
    if unique_messages:
        file_name = f"x{len(unique_messages)}_{source_name.replace(' ', '_')[:50]}.txt"
        
        async with aiofiles.open(file_name, mode='w') as f:
            await f.write("\n".join(unique_messages))
        
        async with aiofiles.open(file_name, mode='rb') as f:
            user_link = await get_user_link(message)
            caption = (
                f"<b>CC Scrapped Successful ✅</b>\n"
                f"<b>━━━━━━━━━━━━━━━━</b>\n"
                f"<b>Source:</b> <code>{source_name} 🌐</code>\n"
                f"<b>Amount:</b> <code>{len(unique_messages)} 📝</code>\n"
                f"<b>Duplicates Removed:</b> <code>{duplicates_removed} 🗑️</code>\n"
            )
            if bin_filter:
                caption += f"<b>📝 BIN Filter:</b> <code>{bin_filter}</code>\n"
            if bank_filter:
                caption += f"<b>📝 Bank Filter:</b> <code>{bank_filter}</code>\n"
            caption += (
                f"<b>━━━━━━━━━━━━━━━━</b>\n"
                f"<b>✅ Card-Scrapped By: {user_link}</b>\n"
            )
            
            try:
                await message.delete()
                await client.send_document(
                    message.chat.id,
                    file_name,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Error sending results: {e}")
                await message.reply_text("Failed to send results. Please try again.")
        
        # Cleanup
        try:
            os.remove(file_name)
        except:
            pass
    else:
        await message.edit_text("<b>Sorry Bro ❌ No Credit Card Found</b>")

async def get_user_link(message):
    if message.from_user is None:
        return '<a href="https://t.me/rmscrapperbot">Smart Tool</a>'
    else:
        user_first_name = message.from_user.first_name or ""
        user_last_name = message.from_user.last_name or ""
        user_full_name = f"{user_first_name} {user_last_name}".strip()
        return f'<a href="tg://user?id={message.from_user.id}">{user_full_name}</a>'

async def join_private_chat(client, invite_link):
    try:
        await client.join_chat(invite_link)
        logger.info(f"Joined chat via invite link: {invite_link}")
        return True
    except UserAlreadyParticipant:
        logger.info(f"Already a participant in the chat: {invite_link}")
        return True
    except InviteRequestSent:
        logger.info(f"Join request sent to the chat: {invite_link}")
        return False
    except (InviteHashExpired, InviteHashInvalid, PeerIdInvalid) as e:
        logger.error(f"Failed to join chat {invite_link}: {e}")
        return False

def setup_handlers(app):
    @app.on_message(filters.command(["scr", "ccscr", "scrcc"], prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
    async def scr_cmd(client, message):
        args = message.text.split()[1:]
        
        if len(args) < 2:
            await message.reply_text(
                "<b>⚠️ Provide channel username and amount to scrape ❌</b>\n\n"
                "<b>Usage:</b> <code>/scr @channel 100</code>\n"
                "<b>Optional:</b> Add BIN number or bank name for filtering"
            )
            return

        channel_identifier = args[0]
        try:
            limit = int(args[1])
        except ValueError:
            await message.reply_text("<b>⚠️ Invalid limit value. Please provide a valid number ❌</b>")
            return

        # Get user ID for limit check
        user_id = message.from_user.id if message.from_user else None
        max_lim = ADMIN_LIMIT if user_id in ADMIN_IDS else DEFAULT_LIMIT
        
        if limit > max_lim:
            await message.reply_text(f"<b>Sorry Bro! Max limit is {max_lim} ❌</b>")
            return

        # Check optional filters
        start_number = None
        bank_name = None
        if len(args) > 2:
            if args[2].isdigit():
                start_number = args[2]
                if len(start_number) < 6:
                    await message.reply_text("<b>⚠️ BIN filter must be at least 6 digits ❌</b>")
                    return
            else:
                bank_name = " ".join(args[2:])

        # Send initial message
        temp_msg = await message.reply_text("<b>Checking channel...</b>")
        
        try:
            # Get chat info
            chat = await safe_get_chat(user, channel_identifier)
            if not chat:
                await temp_msg.edit_text("<b>Hey Bro! 🥲 Invalid username/link or I don't have access ❌</b>")
                return
            
            # Check if it's a private channel that needs joining
            if hasattr(chat, 'invite_link') and chat.invite_link and not chat.username:
                await temp_msg.edit_text("<b>Joining private channel...</b>")
                joined = await join_private_chat(user, chat.invite_link)
                if not joined:
                    await temp_msg.edit_text("<b>Sent join request. Please approve and try again ✅</b>")
                    return
            
            # Start scraping
            await temp_msg.edit_text("<b>Scraping in progress... ⏳</b>")
            scraped_messages = await scrape_messages(user, chat.id, limit, start_number, bank_name)
            unique_messages, duplicates_removed = remove_duplicates(scraped_messages)
            
            if not unique_messages:
                await temp_msg.edit_text("<b>Sorry Bro ❌ No Credit Card Found</b>")
            else:
                bin_filter = start_number[:6] if start_number else None
                await send_results(
                    client, 
                    temp_msg, 
                    unique_messages, 
                    duplicates_removed, 
                    chat.title, 
                    bin_filter, 
                    bank_name
                )
                
        except FloodWait as e:
            await temp_msg.edit_text(f"<b>⚠️ Flood wait: Please wait {e.value} seconds</b>")
        except Exception as e:
            logger.error(f"Error in scr_cmd: {e}")
            await temp_msg.edit_text("<b>Error occurred. Please try again ❌</b>")

    @app.on_message(filters.command(["mc", "multiscr", "mscr"], prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
    async def mc_cmd(client, message):
        args = message.text.split()[1:]
        
        if len(args) < 2:
            await message.reply_text(
                "<b>⚠️ Provide at least one channel and limit</b>\n\n"
                "<b>Usage:</b> <code>/mc @channel1 @channel2 100</code>"
            )
            return

        # Last argument is the limit
        try:
            limit = int(args[-1])
        except ValueError:
            await message.reply_text("<b>⚠️ Invalid limit value. Please provide a valid number ❌</b>")
            return

        # Get user ID for limit check
        user_id = message.from_user.id if message.from_user else None
        max_lim = ADMIN_LIMIT if user_id in ADMIN_IDS else DEFAULT_LIMIT
        
        if limit > max_lim:
            await message.reply_text(f"<b>Sorry Bro! Max limit is {max_lim} ❌</b>")
            return

        # Channel identifiers are all arguments except the last one
        channel_identifiers = args[:-1]
        
        temp_msg = await message.reply_text("<b>Starting multi-channel scrape... ⏳</b>")
        all_messages = []
        
        for idx, channel_identifier in enumerate(channel_identifiers):
            try:
                await temp_msg.edit_text(f"<b>Scraping channel {idx+1}/{len(channel_identifiers)}...</b>")
                chat = await safe_get_chat(user, channel_identifier)
                
                if chat:
                    messages = await scrape_messages(user, chat.id, limit // len(channel_identifiers))
                    all_messages.extend(messages)
                else:
                    logger.warning(f"Could not access channel: {channel_identifier}")
            except Exception as e:
                logger.error(f"Error scraping {channel_identifier}: {e}")
                continue
        
        unique_messages, duplicates_removed = remove_duplicates(all_messages)
        unique_messages = unique_messages[:limit]
        
        if not unique_messages:
            await temp_msg.edit_text("<b>Sorry Bro ❌ No Credit Card Found</b>")
        else:
            await send_results(
                client, 
                temp_msg, 
                unique_messages, 
                duplicates_removed, 
                f"{len(channel_identifiers)} Channels"
            )

    @app.on_message(filters.command("start", prefixes=["/", ".", ",", "!"]) & (filters.group | filters.private))
    async def start(client, message):
        buttons = [
            [InlineKeyboardButton("Update Channel", url="https://t.me/everythingreset"), 
             InlineKeyboardButton("Dev", user_id=1318826936)]
        ]
        await message.reply_text(
            START_MESSAGE,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def main():
    # Start both clients
    await user.start()
    await app.start()
    
    # Set up handlers
    setup_handlers(app)
    
    logger.info("Bot started successfully!")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
