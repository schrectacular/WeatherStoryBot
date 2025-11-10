import requests
import os
import hashlib
import boto3
from datetime import datetime
from zoneinfo import ZoneInfo
from botocore.exceptions import ClientError

# --- Configuration ---
# Fetched from environment variables set in the GitHub Actions workflow
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
IMAGE_URL = 'https://www.weather.gov/images/gsp/WxStory/WeatherStory1.gif'
AWS_REGION = os.environ['AWS_REGION']
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
EASTERN_TZ = ZoneInfo('America/New_York')

# --- AWS DynamoDB Client Initialization ---
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

def send_telegram_photo(image_content):
    """Sends the provided image content to the Telegram chat"""
    telegram_url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto'
    files = {'photo': ('weatherstory.gif', image_content, 'image/gif')}
    data = {'chat_id': CHAT_ID}
    
    try:
        response = requests.post(telegram_url, files=files, data=data)
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        print("Weather image sent successfully to Telegram!")
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
    
    # Fetch the new image from the weather service
    print(f"Fetching image from {IMAGE_URL}...")
    try:
        response = requests.get(IMAGE_URL, timeout=15)
        response.raise_for_status()
        image_content = response.content
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch image: {e}")
        return

    # Calculate the SHA256 hash of the new image to detect changes.
    current_image_hash = hashlib.sha256(image_content).hexdigest()
    
    # Compare hashes to see if the image is new
    if current_image_hash == last_image_hash:
        print("Image has not changed since the last check. No update needed.")
    else:
        print("New weather image detected! Sending to Telegram.")
        send_telegram_photo(image_content)
        # On successful send, update DynamoDB with today's date and the new hash
        # to prevent re-sending.
        update_run_info(today_str, current_image_hash)

if __name__ == '__main__':
    main()
