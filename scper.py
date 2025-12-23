import re
import os
import asyncio
from urllib.parse import urlparse
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from config import API_ID, API_HASH, SESSION_STRING, BOT_TOKEN, ADMIN_IDS, DEFAULT_LIMIT, ADMIN_LIMIT

# Initialize the bot and user clients
bot = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=3000,
    parse_mode=ParseMode.HTML
)

user = Client(
    "user_session",
    session_string=SESSION_STRING,
    workers=3000
)

scrape_queue = asyncio.Queue()

def remove_duplicates(messages):
    unique_messages = list(set(messages))
    duplicates_removed = len(messages) - len(unique_messages)
    return unique_messages, duplicates_removed

async def scrape_messages(client, channel_username, limit, start_number=None):
    messages = []
    count = 0
    # -----------------------------------------------------------
    # EDITED FOR AMEX SUPPORT
    # \d{15,16} allows both Amex (15) and Visa/MC (16)
    # \d{1,2} allows months like '05' or '5'
    # -----------------------------------------------------------
    pattern = r'\d{15,16}\D*\d{1,2}\D*\d{2,4}\D*\d{3,4}'
    
    # Note: user.search_messages might not work as intended for pure history iteration without a query in some versions.
    # If this loop doesn't return messages, consider switching to user.get_chat_history(channel_username)
    async for message in user.search_messages(channel_username):
        if count >= limit:
            break
        text = message.text if message.text else message.caption
        if text:
            matched_messages = re.findall(pattern, text)
            if matched_messages:
                formatted_messages = []
                for matched_message in matched_messages:
                    extracted_values = re.findall(r'\d+', matched_message)
                    if len(extracted_values) == 4:
                        card_number, mo, year, cvv = extracted_values
                        
                        # Basic Validation to ensure cleaner results
                        if len(card_number) in [15, 16] and (1 <= int(mo) <= 12):
                            year = year[-2:] # Get last 2 digits of year
                            # Format nicely
                            formatted_messages.append(f"{card_number}|{mo}|{year}|{cvv}")
                            
                messages.extend(formatted_messages)
                count += len(formatted_messages)
    if start_number:
        messages = [msg for msg in messages if msg.startswith(start_number)]
    messages = messages[:limit]
    return messages

@bot.on_message(filters.command(["scr"]))
async def scr_cmd(client, message):
    args = message.text.split()[1:]
    if len(args) < 2 or len(args) > 3:
        await message.reply_text("<b>⚠️ Provide channel username and amount to scrape</b>")
        return
    channel_identifier = args[0]
    limit = int(args[1])
    max_lim = ADMIN_LIMIT if message.from_user.id in ADMIN_IDS else DEFAULT_LIMIT
    if limit > max_lim:
        await message.reply_text(f"<b>Sorry Bro! Amount over Max limit is {max_lim} ❌</b>")
        return
    start_number = args[2] if len(args) == 3 else None
    parsed_url = urlparse(channel_identifier)
    channel_username = parsed_url.path.lstrip('/') if not parsed_url.scheme else channel_identifier
    try:
        chat = await user.get_chat(channel_username)
        channel_name = chat.title
    except Exception:
        await message.reply_text("<b>Hey Bro! 🥲 Incorrect username ❌</b>")
        return
    temporary_msg = await message.reply_text("<b>Scraping in progress wait.....</b>")
    scrapped_results = await scrape_messages(user, chat.id, limit, start_number)
    unique_messages, duplicates_removed = remove_duplicates(scrapped_results)
    if unique_messages:
        file_name = f"x{len(unique_messages)}_{channel_name.replace(' ', '_')}.txt"
        with open(file_name, 'w') as f:
            f.write("\n".join(unique_messages))
        with open(file_name, 'rb') as f:
            caption = (
                f"<b>CC Scrapped Successful ✅</b>\n"
                f"<b>━━━━━━━━━━━━━━━━</b>\n"
                f"<b>Source:</b> <code>{channel_name}</code>\n"
                f"<b>Amount:</b> <code>{len(unique_messages)}</code>\n"
                f"<b>Duplicates Removed:</b> <code>{duplicates_removed}</code>\n"
                f"<b>━━━━━━━━━━━━━━━━</b>\n"
                f"<b>Card-Scrapper By: <a href='https://t.me/iwillgoforwardsalone'>Dev</a></b>\n"
            )
            await temporary_msg.delete()
            await client.send_document(message.chat.id, f, caption=caption)
        os.remove(file_name)
    else:
        await temporary_msg.delete()
        await client.send_message(message.chat.id, "<b>Sorry Bro ❌ No Credit Card Found</b>")

if __name__ == "__main__":
    print("Bot Started...")
    user.start()
    bot.run()
