from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler, CallbackContext
import re
from telegram import Update
import time
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.proxy import Proxy, ProxyType
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, ConversationHandler, MessageHandler, Filters, CallbackQueryHandler
import csv
from io import StringIO
from telegram import ReplyKeyboardMarkup, KeyboardButton



CSV_FILE_PATH = 'uscis_cases.csv'

SELECTING_ACTION, ENTERING_CASE_NUMBER, SELECTING_CASE = range(3)
MAX_RETRIES = 3

# Load environment variables from .env file
load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TODAY = datetime.now().strftime('%b %d, %Y')
USCIS_URL = 'https://egov.uscis.gov/'
RECEIPT_NUMBER = os.environ.get('RECEIPT_NUMBER', '')




PATTERNS_TO_REMOVE = [
    re.compile(r'Enter Another Receipt Number'),
    re.compile(r'Check Status'),
    re.compile(r'Already have an Account\? Login'),
    re.compile(r'Create an Account\? Sign up'),
    re.compile(r'Check Case Status'),
    re.compile(r'Use this tool to track the status of an immigration application, petition, or request\.'),
    re.compile(r'The receipt number is a unique 13-character identifier that consists of three letters and 10 numbers\. Omit dashes \("-"\) when entering a receipt number\. However, you can include all other characters, including asterisks \("\*"\), if they are listed on your notice as part of the receipt number\. When a receipt number is entered, the check status button will be enabled and you can check the status\.'),
    re.compile(r'Enter a Receipt Number'),
]

switched_to_spanish = False

firefox_options = FirefoxOptions()
firefox_options.headless = True  # Run Firefox in headless mode (no GUI)

# Create a new WebDriver instance for Firefox
driver = webdriver.Firefox(options=firefox_options, executable_path='C:/Users/Administrator/Downloads/geckodriver-v0.33.0-win64/geckodriver.exe')

# Define the constant for maximum retries
MAX_RETRIES = 3

# List of proxies in the format: IP:Port:Username:Password
PROXIES = [""]

# Helper function to create a proxy
def create_proxy(proxy_str):
    proxy_info = proxy_str.split(':')

    proxy = webdriver.Proxy()
    proxy.proxy_type = webdriver.common.proxy.ProxyType.MANUAL
    proxy.http_proxy = f'http://{proxy_info[2]}:{proxy_info[3]}@{proxy_info[0]}:{proxy_info[1]}'
    proxy.ssl_proxy = f'http://{proxy_info[2]}:{proxy_info[3]}@{proxy_info[0]}:{proxy_info[1]}'
    return proxy
    
def start(update: Update, context: CallbackContext):
    context.user_data['state'] = SELECTING_ACTION
    update.message.reply_text('Welcome to USCIS Status Checker Bot! Press the "/caso" button to check the case status.')
# /caso command button click handler

def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == 'enter_case_number':
        query.edit_message_text('Por favor, ingrese el número de caso en el siguiente formato: ABC1234567890')
        context.user_data['state'] = ENTERING_CASE_NUMBER
    else:
        receipt_number = query.data  # Assuming the receipt number is passed as the callback data of each button

        # Reset the user's state
        context.user_data['state'] = SELECTING_ACTION

        # Execute the script with the selected receipt number
        context.args = [receipt_number]
        send_telegram_message(update, context)

# Helper function to switch language
def switch_to_language(driver, language_xpath):
    try:
        # Find the language switch link by XPath
        language_link = driver.find_element('xpath', language_xpath)

        # Click the link to switch the language
        language_link.click()

        # Wait for a moment to allow the language switch to take effect
        time.sleep(5)

        return True  # Language switch successful
    except WebDriverException as e:
        print(f'Error during language switch: {e}')
        return False

# Helper function to get current language
def get_current_language(driver):
    try:
        # Find the language switch link by XPath
        language_link = driver.find_element('xpath', '//*[@id="alt-lang-link"]/a')

        # Get the lang attribute value
        current_language = language_link.get_attribute('lang')

        return current_language
    except NoSuchElementException:
        print('Language link not found')
        return None

# Helper function to navigate and retry with proxy
def navigate_and_retry_with_proxy(driver, url, proxy):
    for attempt in range(MAX_RETRIES):
        try:
            # Set proxy for the WebDriver
            capabilities = webdriver.DesiredCapabilities.FIREFOX.copy()
            proxy.add_to_capabilities(capabilities)

            # Navigate to the USCIS status check page
            print(f'Attempt {attempt + 1}: Navigating to {url} with proxy')
            driver.get(url)
            return True  # If navigation succeeds, return True
        except WebDriverException as e:
            print(f'Error during navigation: {e}')
            if attempt < MAX_RETRIES - 1:
                # If not the last attempt, wait for a moment before retrying
                print(f'Waiting before retrying...')
                time.sleep(5)
            else:
                return False

# Helper function to save data to CSV
def save_to_csv(user_id, receipt_number, date, status):
    # Check if the CSV file exists, create it if not
    if not os.path.isfile(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, 'w', newline='') as csv_file:
            csv_writer = csv.writer(csv_file)
            # Write header to the CSV file
            csv_writer.writerow(['User_ID', 'Receipt_Number', 'Date', 'Status'])

    # Append the new data to the CSV file
    with open(CSV_FILE_PATH, 'a', newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([user_id, receipt_number, date, status])

# Helper function to load user cases from CSV
def load_user_cases(user_id):
    # Load user's cases from the CSV file
    user_cases = []
    if os.path.isfile(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, 'r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                if str(row['User_ID']) == str(user_id):  # Compare as strings
                    user_cases.append(row)
    return user_cases

def send_telegram_message(update, context):
    global switched_to_spanish  # Declare the global variable

    try:
        # Get the receipt number from the command arguments
        receipt_number = context.args[0] if context.args and len(context.args) > 0 else None

        if receipt_number:
            for proxy_str in PROXIES:
                # Create a new proxy for each navigation
                proxy = create_proxy(proxy_str)

                # Attempt navigation with proxy
                if navigate_and_retry_with_proxy(driver, USCIS_URL, proxy):

                    # Check if the language switch to Español has already occurred
                    if not switched_to_spanish:
                        # Switch language to Español
                        if switch_to_language(driver, '//*[@id="alt-lang-link"]/a'):
                            print('Switched to Español')
                            switched_to_spanish = True  # Set the flag to True
                        else:
                            print('Failed to switch language to Español')

                    # Input the receipt number
                    print(f'Inputting receipt number {receipt_number}')
                    driver.find_element('id', 'receipt_number').send_keys(receipt_number, Keys.RETURN)

                    # Wait for 10 seconds to load the status
                    time.sleep(15)

                    # Get and print the status
                    print('Getting status')
                    status_text = driver.find_element('class name', 'caseStatusSection').text

                    # Remove unnecessary patterns
                    for pattern in PATTERNS_TO_REMOVE:
                        status_text = re.sub(pattern, '', status_text).strip()

                    # Print the status
                    message = f'{TODAY}: {status_text}'
                    print(message)

                    # Save the status to the CSV file
                    if update.message:
                        save_to_csv(update.message.chat_id, receipt_number, TODAY, status_text)

                    # Send the status message to Telegram
                    if update.message:
                        print('Sending message to Telegram...')
                        print(f'Chat ID: {update.message.chat_id}')
                        context.bot.send_message(chat_id=update.message.chat_id, text=message)
                        print('Message sent to Telegram.')

                else:
                    print(f'Failed to navigate to {USCIS_URL} with proxy')

        else:
            if update.message:
                context.bot.send_message(chat_id=update.message.chat_id, text="Please provide a valid receipt number.")
    except Exception as e:
        print(f"Error: {e}")
        if update.message:
            print('Error sending message to Telegram.')
            context.bot.send_message(chat_id=update.message.chat_id, text="Error fetching USCIS status. Please try again later.")




# /caso command handler
def caso(update: Update, context: CallbackContext):
    # Define custom command buttons with Spanish text
    buttons = [
        [KeyboardButton("/caso <numero_de_recibo>")],
        [KeyboardButton("/ver_casos")],
    ]

    # Create the keyboard layout
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)

    # Send the message with the keyboard
    update.message.reply_text('Por favor, inserta el número de caso en el siguiente formato: ABC1234567890', reply_markup=reply_markup)

    # Set the user's state to ENTERING_CASE_NUMBER
    context.user_data['state'] = ENTERING_CASE_NUMBER


def view_cases(update: Update, context: CallbackContext):
    # Load user cases from CSV
    user_id = update.message.chat_id
    user_cases = load_user_cases(user_id)

    # Check if the user has any cases
    if user_cases:
        # Extract receipt numbers from user cases
        receipt_numbers = [case['Receipt_Number'] for case in user_cases]

        # Create a list of InlineKeyboardButtons with receipt numbers
        buttons = [InlineKeyboardButton(receipt_number, callback_data=receipt_number) for receipt_number in receipt_numbers]

        # Create the keyboard layout
        reply_markup = InlineKeyboardMarkup([buttons])

        update.message.reply_text('Seleccione el número del caso que desea ver:', reply_markup=reply_markup)

        # Set the user's state to SELECTING_CASE
        context.user_data['state'] = SELECTING_CASE
    else:
        update.message.reply_text('No se encontraron casos. Use /caso para agregar uno nuevo.')
        return



# Change the parameter name from query to update
def select_case(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    user_id = query.message.chat_id
    user_cases = load_user_cases(user_id)

    # Check if there are cases to display
    if not user_cases:
        query.edit_message_text('No se encontraron casos. Use /caso para agregar uno nuevo.')
        return

    # Execute the script for each case in the list
    for index, case in enumerate(user_cases):
        receipt_number = case['Receipt_Number']

        # Execute the script with the selected receipt number
        context.args = [receipt_number]
        send_telegram_message(query, context, receipt_number)

        # Wait for a moment before processing the next case (you can adjust the wait time)
        time.sleep(5)

    # Reset the user's state
    context.user_data['state'] = SELECTING_ACTION

    # Remove the custom keyboard after executing the script for all cases
    reply_markup = InlineKeyboardMarkup([])  # Empty InlineKeyboardMarkup to remove the buttons
    query.edit_message_text('Fetching USCIS status for all cases...', reply_markup=reply_markup)





# /cancel command handler to cancel the conversation
def cancel(update: Update, context: CallbackContext):
    context.user_data.clear()
    update.message.reply_text('Conversación cancelada.')

# Handle text input during the conversation
def handle_text_input(update: Update, context: CallbackContext):
    user_state = context.user_data.get('state')

    if user_state == ENTERING_CASE_NUMBER:
        # Get the entered case number
        case_number = update.message.text.strip()

        # Validate the case number (you can add more validation logic)
        if len(case_number) == 13 and case_number.isalnum():
            # Execute the script with the entered case number
            context.args = [case_number]
            send_telegram_message(update, context)
        else:
            update.message.reply_text('Número de caso no válido. Por favor, inténtelo de nuevo.')

        # Reset the user's state
        context.user_data['state'] = SELECTING_ACTION
    else:
        # Handle other cases or show a message indicating the expected action
        update.message.reply_text('Seleccione una acción primero.')

# Main function
if __name__ == '__main__':
    updater = Updater(token='BotToken', use_context=True)
    dp = updater.dispatcher

    # Add handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("caso", caso))
    dp.add_handler(CallbackQueryHandler(button_click))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_input))
    
    # Add the conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('ver_casos', view_cases)],
        states={
            SELECTING_CASE: [MessageHandler(Filters.text & ~Filters.command, select_case)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dp.add_handler(conv_handler)

    updater.start_polling()
    updater.idle()

    # Quit the browser outside the main loop
    driver.quit()