import os
import json
import logging
import requests
import telebot
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

#===============================================
#================= CONFIGURATION ===============
#===============================================

WATCHLIST_FILE = 'watchlist.json'
NOTIFICATIONS_FILE = 'notifications.json'
ITEMS_PER_PAGE = 5

# Configure logging
logging.basicConfig(filename='crypto_tracker.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_KEY')
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

#===============================================
#================= UTILITY FUNCTIONS ============
#===============================================

def load_json_file(file_name):
    """
    Loads JSON data from a file.

    Args:
        file_name (str): The path to the JSON file.

    Returns:
        dict: The data loaded from the JSON file, or an empty dictionary if the file does not exist or is invalid.
    """
    logging.info(f"Loading JSON file: {file_name}")
    if not os.path.exists(file_name):
        logging.warning(f"{file_name} does not exist.")
        return {}
    try:
        with open(file_name, 'r') as file:
            data = json.load(file)
            logging.debug(f"Loaded data: {data}")
            return data
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for file {file_name}: {e}")
        return {}

def save_json_file(file_name, data):
    """
    Saves JSON data to a file.

    Args:
        file_name (str): The path to the JSON file.
        data (dict): The data to save to the JSON file.

    Returns:
        None
    """
    logging.info(f"Saving data to JSON file: {file_name}")
    try:
        with open(file_name, 'w') as file:
            json.dump(data, file, indent=4)
            logging.debug(f"Saved data: {data}")
    except IOError as e:
        logging.error(f"Error saving JSON file {file_name}: {e}")
        
def get_token_info(token_address, network):
    """
    Retrieves token details (network, name, and symbol) using the DEX Screener API.

    Args:
        token_address (str): The contract address of the token.
        network (str): The network where the token is deployed.

    Returns:
        tuple: A tuple containing the network (chainId), symbol, and name of the token. 
               Returns (None, None, None) if the token details are not found or an error occurs.
    """
    base_url = "https://api.dexscreener.com/latest/dex/tokens/"
    url = f"{base_url}{token_address}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an exception for HTTP errors
        data = response.json()

        logging.debug(f"API response for {network} token: {data}")
        
        # Check if 'pairs' key exists in the data
        if 'pairs' in data:
            for pair in data['pairs']:
                base_token = pair['baseToken']
                # Check if the base token's address matches the provided token address
                if base_token['address'].lower() == token_address.lower():
                    # Returning network (chainId), symbol, and name
                    return pair['chainId'], base_token['symbol'], base_token['name']
        logging.error(f"No matching token details found for {token_address}.")
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get token info for {token_address}: {e}")
    return None, None, None

def get_crypto_price(token_address):
    """
    Retrieves the token price in USD using the DEX Screener API.

    Args:
        token_address (str): The contract address of the token.

    Returns:
        str: The price of the token in USD, or 'N/A' if the price information is not found or an error occurs.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an exception for HTTP errors
        data = response.json()
        
        # Check if 'pairs' key exists in the data
        if 'pairs' in data:
            for pair in data['pairs']:
                base_token = pair['baseToken']
                # Check if the base token's address matches the provided token address
                if base_token['address'].lower() == token_address.lower():
                    # Returning the price in USD
                    return pair.get('priceUsd', 'N/A')
        
        logging.error(f"No price information found for token {token_address}.")
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get crypto price for {token_address}: {e}")
        return 'N/A'