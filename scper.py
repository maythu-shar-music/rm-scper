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
    workers=1000,
    parse_mode=ParseMode.HTML
)

user = Client(
    "user_session",
    session_string=SESSION_STRING,
    workers=1000
)

scrape_queue = asyncio.Queue()

def remove_duplicates(messages):
    unique_messages = list(set(messages))
    duplicates_removed = len(messages) - len(unique_messages)
    return unique_messages, duplicates_removed

async def scrape_messages(client, channel_identifier, limit, start_number=None):
    messages = []
    count = 0
    pattern = r'\d{15,16}\D*\d{1,2}\D*\d{2,4}\D*\d{3,4}'
    
    try:
        async for message in client.get_chat_history(channel_identifier, limit=limit*10):
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
    except Exception as e:
        print(f"Error scraping messages: {e}")
        return []
    
    if start_number:
        messages = [msg for msg in messages if msg.startswith(start_number)]
    messages = messages[:limit]
    return messages

@bot.on_message(filters.command(["start"]))
async def start_cmd(client, message):
    """Welcome message for /start command"""
    user_name = message.from_user.first_name
    welcome_text = f"""
<b>👋 Hello {user_name}!</b>

<b>Welcome to Card Scrapper Bot</b>

<b>📌 Available Commands:</b>
• <code>/scr [username] [amount]</code> - Scrape CC from channel
• <code>/scr [username] [amount] [start_number]</code> - Scrape with starting number

<b>📝 Examples:</b>
<code>/scr @channel_name 100</code>
<code>/scr @channel_name 50 43</code>

<b>⚠️ Note:</b>
• Max limit: <code>{DEFAULT_LIMIT}</code> for users
• Max limit: <code>{ADMIN_LIMIT}</code> for admins
• Only for educational purposes

<b>👨‍💻 Developer:</b> <a href='https://t.me/iwillgoforwardsalone'>Dev</a>
    """
    
    await message.reply_text(
        welcome_text,
        disable_web_page_preview=True
    )

@bot.on_message(filters.command(["help"]))
async def help_cmd(client, message):
    """Help message"""
    help_text = """
<b>🆘 Help Guide</b>

<b>Usage:</b>
<code>/scr [channel_username] [amount]</code>

<b>Parameters:</b>
• <b>channel_username:</b> Channel username or ID (with @ or -100)
• <b>amount:</b> Number of CCs to scrape
• <b>start_number:</b> Optional - Filter by starting numbers

<b>Examples:</b>
1. <code>/scr @testchannel 100</code>
2. <code>/scr -1001234567890 50</code>
3. <code>/scr @channel 30 43</code> (43 နဲ့စတဲ့ CCs ကိုပဲယူမယ်)

<b>Support:</b> Contact @iwillgoforwardsalone
    """
    
    await message.reply_text(
        help_text,
        disable_web_page_preview=True
    )

@bot.on_message(filters.command(["scr"]))
async def scr_cmd(client, message):
    args = message.text.split()[1:]
    if len(args) < 2 or len(args) > 3:
        await message.reply_text("<b>⚠️ Provide channel username and amount to scrape</b>\n\nExample: <code>/scr @channel_name 100</code>")
        return
    channel_identifier = args[0]
    limit = int(args[1])
    max_lim = ADMIN_LIMIT if message.from_user.id in ADMIN_IDS else DEFAULT_LIMIT
    if limit > max_lim:
        await message.reply_text(f"<b>Sorry Bro! Amount over Max limit is {max_lim} ❌</b>")
        return
    start_number = args[2] if len(args) == 3 else None
    
    # Parse channel identifier
    if channel_identifier.startswith("https://t.me/"):
        channel_username = channel_identifier.split("/")[-1]
    else:
        channel_username = channel_identifier
    
    temporary_msg = await message.reply_text("<b>Scraping in progress wait.....</b>")
    
    try:
        # Try to get chat info first
        try:
            chat = await user.get_chat(channel_username)
            channel_name = chat.title
        except Exception as e:
            # If username doesn't work, try as ID
            try:
                chat = await user.get_chat(int(channel_username))
                channel_name = chat.title
            except:
                channel_name = channel_username
        
        # Scrape messages
        scrapped_results = await scrape_messages(user, chat.id if hasattr(chat, 'id') else channel_username, limit, start_number)
        
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
    
    except Exception as e:
        await temporary_msg.delete()
        await client.send_message(message.chat.id, f"<b>Error: {str(e)}</b>")

# About command
@bot.on_message(filters.command(["about"]))
async def about_cmd(client, message):
    about_text = """
<b>🤖 About This Bot</b>

<b>Name:</b> Card Scrapper Bot
<b>Version:</b> 1.0
<b>Purpose:</b> Educational scraping tool
<b>Developer:</b> @iwillgoforwardsalone

<b>⚠️ Disclaimer:</b>
This bot is for educational purposes only.
Use at your own risk.
    """
    await message.reply_text(about_text)

if __name__ == "__main__":
    print("Bot Started...")
    user.start()
    bot.run()
