import requests
import os
import hashlib
import boto3
from datetime import datetime
from zoneinfo import ZoneInfo
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup

# --- Configuration ---
# Fetched from environment variables set in the GitHub Actions workflow
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
# We'll scrape the image location from this URL rather than defining it. They keep switching between .png and .gif
WEATHER_STORY_URL = 'https://www.weather.gov/gsp/weatherstory'
AWS_REGION = os.environ['AWS_REGION']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
EASTERN_TZ = ZoneInfo('America/New_York')

# --- AWS DynamoDB Client Initialization ---
# The script relies on 'boto3' and 'beautifulsoup4' being available in the environment.
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)
# The primary key of our table is 'setting', and we'll use a single item 'image_status'
# to track the state of our bot.
PRIMARY_KEY = {'setting': 'image_status'}

def get_last_run_info():
    """Fetches the last run date and image hash from DynamoDB"""
    try:
        response = table.get_item(Key=PRIMARY_KEY)
        item = response.get('Item', {})
        # Return the saved date and hash, or None if they don't exist
        return item.get('last_run_date'), item.get('image_hash')
    except ClientError as e:
        print(f"Error getting item from DynamoDB: {e.response['Error']['Message']}")
        # Return None on error to indicate we couldn't get the status
        return None, None

def update_run_info(run_date, image_hash):
    """Updates the run date and image hash in DynamoDB"""
    try:
        table.update_item(
            Key=PRIMARY_KEY,
            UpdateExpression="SET last_run_date = :d, image_hash = :h",
            ExpressionAttributeValues={
                ':d': run_date,
                ':h': image_hash
            }
        )
        print(f"Successfully updated DynamoDB with date: {run_date} and new hash")
    except ClientError as e:
        print(f"Error updating item in DynamoDB: {e.response['Error']['Message']}")

def extract_story_content():
    """
    Fetches the HTML from the weather story page and extracts the image URL and description.
    Returns a tuple: (image_url, description_text) or (None, None) on failure.
    """
    print(f"Fetching HTML from {WEATHER_STORY_URL}...")
    try:
        response = requests.get(WEATHER_STORY_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the main container div with class 'graphicast'
        graphicast_div = soup.find('div', class_='graphicast')
        
        if not graphicast_div:
            print("Error: Could not find the 'graphicast' div in the HTML.")
            return None, None
            
        # Find the image URL
        image_tag = graphicast_div.find('img')
        image_url = image_tag.get('src') if image_tag else None

        # Find the description text
        description_tag = graphicast_div.find('div', class_='description')
        description_text = description_tag.get_text(strip=True) if description_tag else ""

        if not image_url:
            print("Error: Could not find the image source URL.")
            return None, None

        print(f"Extracted Image URL: {image_url}")
        print(f"Extracted Description: {description_text}")
        
        return image_url, description_text
        
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch HTML: {e}")
        return None, None
    except Exception as e:
        print(f"An error occurred during HTML parsing: {e}")
        return None, None


def send_telegram_photo(image_content, caption_text):
    """Sends the provided image content and a caption to the Telegram chat"""
    telegram_url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto'
    
    # Get the file extension and use it for the MIME type, defaulting to PNG
    # The file name in the tuple is just a hint to Telegram
    file_ext = 'png' 
    if image_content.startswith(b'\x89PNG') or image_content.startswith(b'\xFF\xD8'): # Check for PNG or JPEG magic bytes (quick check)
        # We don't really care as Telegram handles the content type based on the file extension and content
        pass
    elif image_content.startswith(b'GIF8'):
        file_ext = 'gif'
    
    mime_type = f'image/{file_ext}'
    
    files = {'photo': (f'weatherstory.{file_ext}', image_content, mime_type)}
    data = {
        'chat_id': CHAT_ID,
        'caption': caption_text,
    }
    
    try:
        response = requests.post(telegram_url, files=files, data=data)
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        print("Weather image and description sent successfully to Telegram!")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send image to Telegram: {e}")

def main():
    """Main function to check for and send new weather images"""
    now_eastern = datetime.now(EASTERN_TZ)
    today_str = now_eastern.strftime('%Y-%m-%d')
    
    # Time check: Only run after 3 AM Eastern Time
    if now_eastern.hour < 3:
        print(f"Current time is {now_eastern.strftime('%H:%M:%S')} ET. It's before 3 AM. Skipping.")
        return

    print(f"Running check at {now_eastern.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    # Fetch previous run info from dynamoDB
    last_run_date, last_image_hash = get_last_run_info()
    
    # Extract image URL and description from the source HTML
    image_url, description_text = extract_story_content()
    
    if not image_url:
        print("Could not retrieve image URL or description. Exiting.")
        return
    
    # Fetch the new image content using the dynamically found URL
    print(f"Fetching image content from {image_url}...")
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        image_content = response.content
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch image content: {e}")
        return

    # Calculate the SHA256 hash of the new image content.
    current_image_hash = hashlib.sha256(image_content).hexdigest()
    
    # Compare hashes to see if the image is new. We only check the image hash.
    if current_image_hash == last_image_hash:
        print("Image content has not changed since the last check. No update needed.")
    else:
        print("New weather image detected! Sending to Telegram.")
        send_telegram_photo(image_content, description_text)
        
        # On successful send, update DynamoDB with today's date and the new hash
        update_run_info(today_str, current_image_hash)

if __name__ == '__main__':
    main()
