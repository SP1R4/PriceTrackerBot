import time
import logging
import threading
from telebot import types
from utils import (
    load_json_file,
    save_json_file,
    get_token_info,
    get_crypto_price,
    WATCHLIST_FILE,
    NOTIFICATIONS_FILE,
    ITEMS_PER_PAGE,
    bot
)

# In-memory storage for conversation states
user_states = {}

#===============================================
#================= COMMANDS ====================
#===============================================

@bot.message_handler(commands=['start', 'help'])
def start(message):
    """
    Handles /start and /help commands. Provides a welcome message with 
    a list of available commands.
    """
    chat_id = message.chat.id
    user_states[chat_id] = {'state': None}
    bot.send_message(chat_id, "👋 Welcome! Use the following commands:\n"
                              "/addwatchlist - 📈 Add a token to your watchlist\n"
                              "/addnotification - 🔔 Add a notification for a token\n"
                              "/viewwatchlist - 📋 View your watchlist\n"
                              "/viewnotifications - 📩 View your notifications\n"
                              "/removewatchlist - ❌ Remove a token from your watchlist\n"
                              "/removenotification - 🚫 Remove a notification")

@bot.message_handler(commands=['addtoken'])
def handle_add_watchlist(message):
    """
    Initiates the process of adding a token to the watchlist. 
    Prompts the user to select a network.
    """
    chat_id = message.chat.id
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Ethereum (ETH) 🏦", callback_data='network_eth'))
    markup.add(types.InlineKeyboardButton("Solana (SOL) 🌐", callback_data='network_sol'))
    markup.add(types.InlineKeyboardButton("Binance Smart Chain (BSC) 🏗️", callback_data='network_bsc'))
    bot.send_message(chat_id, "🔍 Select the network for the token:", reply_markup=markup)
    user_states[chat_id] = {'state': 'waiting_for_network'}

@bot.callback_query_handler(func=lambda call: call.data.startswith('network_'))
def handle_network_selection(call):
    """
    Handles the user's selection of the cryptocurrency network. 
    Prompts the user to enter the token contract address.
    """
    chat_id = call.message.chat.id
    network = call.data.split('_')[1]
    bot.send_message(chat_id, f"📝 Enter {network.upper()} token contract address:")
    user_states[chat_id] = {'state': 'waiting_for_contract_address', 'network': network}
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_for_contract_address')
def process_contract_address(message):
    """
    Processes the token contract address entered by the user. 
    Adds the token to the watchlist if valid.
    """
    chat_id = message.chat.id
    contract_address = message.text.strip()
    network = user_states.get(chat_id, {}).get('network', None)

    try:
        # Load the current watchlist
        watchlist = load_json_file(WATCHLIST_FILE)
        
        # Check if the token already exists in the watchlist by contract address
        token_exists = any(token['address'].lower() == contract_address.lower() for token in watchlist.values())
        
        if token_exists:
            bot.send_message(chat_id, "❌ This token is already in your watchlist.")
            logging.info(f"Attempted to add a token already in the watchlist: {contract_address}")
        else:
            # Get token info
            crypto_id, symbol, name = get_token_info(contract_address, network)

            if crypto_id:
                # Add token to watchlist
                watchlist[symbol] = {
                    'symbol': symbol.upper(),
                    'network': network,
                    'address': contract_address
                }
                save_json_file(WATCHLIST_FILE, watchlist)
                bot.send_message(chat_id, f"✅ Token added to watchlist: {name} ({symbol.upper()})")
                logging.info(f"Token added to watchlist: {name} ({symbol.upper()})")
            else:
                bot.send_message(chat_id, "❌ Invalid contract address or token not found.")
                logging.error("Invalid contract address or token not found for network: %s, contract address: %s", network, contract_address)
    except Exception as e:
        logging.error("Error processing contract address: %s", str(e))
        bot.send_message(chat_id, "❌ An error occurred while adding the token. Please try again later.")
    finally:
        # Reset user state
        user_states[chat_id]['state'] = None


@bot.message_handler(commands=['addnotification'])
def handle_add_notification(message):
    chat_id = message.chat.id
    watchlist = load_json_file(WATCHLIST_FILE)
    
    if not watchlist:
        bot.send_message(chat_id, "🛑 Your watchlist is empty. Add tokens to your watchlist first.")
        return

    bot.send_message(chat_id, "📝 Enter the symbol of the token for which you want to add a notification:")
    user_states[chat_id] = {'state': 'waiting_for_symbol'}

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_for_symbol')
def process_token_symbol(message):
    chat_id = message.chat.id
    symbol = message.text.strip().upper()
    watchlist = load_json_file(WATCHLIST_FILE)
    
    token = watchlist.get(symbol)
    if token:
        user_states[chat_id] = {
            'state': 'waiting_for_notification_details',
            'symbol': symbol
        }
        bot.send_message(chat_id, f"📝 Enter the notification details for {symbol} (e.g., 'up 10%' or 'down 20%'):")
    else:
        bot.send_message(chat_id, "❌ Token symbol not found in your watchlist.")
        logging.error("Token symbol not found in watchlist: %s", symbol)


@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_for_notification_details')
def process_notification_details(message):
    """
    Processes the notification details entered by the user and adds
    the notification to the system if the format is correct.
    """
    chat_id = message.chat.id
    details = message.text.strip().lower()
    symbol = user_states.get(chat_id, {}).get('symbol')

    logging.info(f"Received notification details: {details} for symbol: {symbol}")

    if not symbol:
        bot.send_message(chat_id, "❌ There was an error retrieving your token details. Please try again.")
        logging.error(f"Error retrieving token details for chat_id: {chat_id}")
        user_states[chat_id]['state'] = None
        return

    if 'up' in details or 'down' in details:
        parts = details.split()
        if len(parts) == 2 and parts[0] in ['up', 'down'] and parts[1].replace('%', '').isdigit():
            change_type = parts[0]
            threshold_percentage = float(parts[1].replace('%', ''))

            notifications = load_json_file(NOTIFICATIONS_FILE)
            logging.debug(f"Current notifications before update: {notifications}")
            
            notifications[symbol] = {
                'chat_id': chat_id,
                'symbol': symbol,
                'change_type': change_type,
                'threshold_percentage': threshold_percentage,
                'previous_price': None
            }

            logging.debug(f"Updated notifications to be saved: {notifications}")

            save_json_file(NOTIFICATIONS_FILE, notifications)
            bot.send_message(chat_id, f"🔔 Notification set: {symbol} will notify when price goes {change_type} by {threshold_percentage}%.")
            logging.info(f"Notification set for {symbol}: {change_type} by {threshold_percentage}%")
        else:
            bot.send_message(chat_id, "❌ Invalid format. Please enter the details again (e.g., 'up 10%' or 'down 20%').")
            logging.error(f"Invalid format received for notification details: {details}")
    else:
        bot.send_message(chat_id, "❌ Invalid format. Please enter the details again (e.g., 'up 10%' or 'down 20%').")
        logging.error(f"Invalid format received for notification details: {details}")

    user_states[chat_id]['state'] = None



def get_paginated_watchlist(watchlist, page):
    """
    Returns a paginated list of watchlist items.
    """
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    items = list(watchlist.items())[start:end]
    return items

def chunked_watchlist(watchlist, chunk_size):
    """
    Yields chunks of the watchlist for pagination.
    """
    for i in range(0, len(watchlist), chunk_size):
        yield dict(list(watchlist.items())[i:i + chunk_size])

@bot.message_handler(commands=['viewwatchlist'])
def view_watchlist(message):
    """
    Handles the /viewwatchlist command. 
    Displays the user's watchlist in a paginated manner.
    """
    chat_id = message.chat.id
    watchlist = load_json_file(WATCHLIST_FILE)

    if not watchlist:
        bot.send_message(chat_id, "🛑 Your watchlist is empty. Add tokens to your watchlist first.")
        return

    user_states[chat_id] = {'state': 'viewing_watchlist', 'page': 1}
    show_watchlist_page(chat_id, 1)

def show_watchlist_page(chat_id, page):
    """
    Shows a specific page of the watchlist.
    """
    watchlist = load_json_file(WATCHLIST_FILE)
    items = get_paginated_watchlist(watchlist, page)
    markup = types.InlineKeyboardMarkup()

    if not items:
        bot.send_message(chat_id, "📄 No more items in your watchlist.")
        return

    for symbol, token in items:
        button = types.InlineKeyboardButton(f"{token['symbol']} ({token['network'].upper()}):{get_crypto_price(token['address'])}$", callback_data=f"watchlist_{symbol}")
        markup.add(button)

    next_button = types.InlineKeyboardButton("➡️ Next", callback_data='watchlist_next')
    prev_button = types.InlineKeyboardButton("⬅️ Previous", callback_data='watchlist_prev')
    markup.add(prev_button, next_button)
    bot.send_message(chat_id, f"📋 Watchlist (Page {page}):", reply_markup=markup)

@bot.message_handler(commands=['viewnotifications'])
def handle_view_notifications(message):
    """
    Sends the user a list of their current notifications.
    """
    chat_id = message.chat.id
    notifications = load_json_file(NOTIFICATIONS_FILE)

    user_notifications = []
    for symbol, notif in notifications.items():
        if notif.get('chat_id') == chat_id:
            user_notifications.append({
                'symbol': notif.get('symbol'),
                'change_type': notif.get('change_type'),
                'threshold_percentage': notif.get('threshold_percentage')
            })

    if not user_notifications:
        bot.send_message(chat_id, "🛑 You have no notifications set.")
        return

    response = "📩 Your Notifications:\n"
    for notif in user_notifications:
        response += f"{notif['symbol']}: Notify when price goes {notif['change_type']} by {notif['threshold_percentage']}%\n"

    bot.send_message(chat_id, response)


@bot.callback_query_handler(func=lambda call: call.data.startswith('watchlist_'))
def handle_watchlist_navigation(call):
    """
    Handles navigation through the watchlist pages.
    """
    chat_id = call.message.chat.id
    state = user_states.get(chat_id, {})
    current_page = state.get('page', 1)

    if call.data == 'watchlist_next':
        show_watchlist_page(chat_id, current_page + 1)
        user_states[chat_id]['page'] = current_page + 1
    elif call.data == 'watchlist_prev' and current_page > 1:
        show_watchlist_page(chat_id, current_page - 1)
        user_states[chat_id]['page'] = current_page - 1

@bot.message_handler(commands=['removewatchlist'])
def handle_remove_watchlist(message):
    """
    Initiates the process of removing a token from the watchlist. 
    Prompts the user to enter the token symbol.
    """
    chat_id = message.chat.id
    watchlist = load_json_file(WATCHLIST_FILE)

    if not watchlist:
        bot.send_message(chat_id, "🛑 Your watchlist is empty.")
        return

    bot.send_message(chat_id, "📝 Enter the symbol of the token you want to remove:")
    user_states[chat_id] = {'state': 'waiting_for_removal_symbol'}

@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_for_removal_symbol')
def process_removal_symbol(message):
    """
    Processes the token symbol entered by the user for removal.
    """
    chat_id = message.chat.id
    symbol = message.text.strip().upper()  # Ensure symbol is uppercase for consistency

    watchlist = load_json_file(WATCHLIST_FILE)
    notifications = load_json_file(NOTIFICATIONS_FILE)

    if symbol in watchlist:
        del watchlist[symbol]
        save_json_file(WATCHLIST_FILE, watchlist)

        # Remove associated notifications
        to_remove = [key for key, val in notifications.items() if val['symbol'] == symbol]
        for key in to_remove:
            del notifications[key]
        save_json_file(NOTIFICATIONS_FILE, notifications)

        bot.send_message(chat_id, f"✅ {symbol} removed from watchlist and notifications.")
        logging.info(f"Removed {symbol} from watchlist and notifications.")
    else:
        bot.send_message(chat_id, "❌ Token symbol not found in your watchlist.")
        logging.error("Token symbol not found in watchlist for removal: %s", symbol)

    # Reset state to avoid repeated handling
    user_states[chat_id]['state'] = None

@bot.message_handler(commands=['removenotification'])
def handle_remove_notification(message):
    """
    Initiates the process of removing a notification.
    Shows a list of user notifications to choose from.
    """
    chat_id = message.chat.id
    notifications = load_json_file(NOTIFICATIONS_FILE)
    
    user_notifications = {symbol: notif for symbol, notif in notifications.items() if notif.get('chat_id') == chat_id}

    if not user_notifications:
        bot.send_message(chat_id, "🛑 You have no notifications set.")
        return

    markup = types.InlineKeyboardMarkup()
    for symbol, notif in user_notifications.items():
        markup.add(types.InlineKeyboardButton(f"{notif['symbol']} 🚫", callback_data=f'remove_notification_{symbol}'))

    bot.send_message(chat_id, "📋 Select the notification to remove:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_notification_'))
def handle_remove_notification_callback(call):
    """
    Handles the callback query for removing a notification.
    """
    chat_id = call.message.chat.id
    symbol = call.data.split('_')[2]

    notifications = load_json_file(NOTIFICATIONS_FILE)
    
    if symbol in notifications and notifications[symbol]['chat_id'] == chat_id:
        del notifications[symbol]
        save_json_file(NOTIFICATIONS_FILE, notifications)
        bot.send_message(chat_id, f"✅ Notification for {symbol} removed.")
        logging.info(f"Notification removed for {symbol}")

    else:
        bot.send_message(chat_id, "❌ Invalid notification selection.")
        logging.error("Invalid notification selection or symbol not found.")

    bot.answer_callback_query(call.id)

def poll_prices():
    while True:
        try:
            watchlist = load_json_file(WATCHLIST_FILE)
            notifications = load_json_file(NOTIFICATIONS_FILE)
            
            for symbol, token in watchlist.items():
                current_price = get_crypto_price(token['address'])
                
                if current_price is None:
                    logging.error(f"Failed to fetch price for {token['symbol']}")
                    continue
                
                if symbol in notifications:
                    notif = notifications[symbol]
                    chat_id = notif['chat_id']
                    change_type = notif['change_type']
                    threshold = notif['threshold_percentage']
                    previous_price = notif.get('previous_price', None)
                    
                    if previous_price:
                        price_change_percentage = ((current_price - previous_price) / previous_price) * 100
                    else:
                        notif['previous_price'] = current_price
                        continue
                    
                    if (change_type == 'up' and price_change_percentage >= threshold) or \
                       (change_type == 'down' and price_change_percentage <= -threshold):
                        bot.send_message(chat_id, f"📈 {symbol} price has gone {change_type} by {threshold}%. Current price: ${current_price:.2f}")
                        logging.info(f"Notification triggered for {symbol}: {change_type} by {threshold}% at price ${current_price:.2f}")

                    notif['previous_price'] = current_price

                    save_json_file(NOTIFICATIONS_FILE, notifications)
        
        except Exception as e:
            logging.error("Error in poll_prices loop: %s", str(e))
        
        time.sleep(300)  # 5 minutes

def main():
    logging.info("Starting the bot and price polling service.")
    
    # Start the poll_prices function in a separate thread
    price_polling_thread = threading.Thread(target=poll_prices)
    price_polling_thread.daemon = True
    price_polling_thread.start()
    
    # Start the bot's polling
    try:
        bot.polling(none_stop=True)
    except KeyboardInterrupt:
        logging.info("Bot stopped.")
    except ConnectionError as e:
        logging.error(f"ConnectionError occurred: {e}. Restart in 15 seconds...")
        time.sleep(15)
        main()
    except Exception as e:
        logging.error(f"Unexpected error: {e}. Restart in 15 seconds...")
        time.sleep(15)
        main()

if __name__ == "__main__":
    main()
