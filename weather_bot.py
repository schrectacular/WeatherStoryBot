import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo

def send_weather_image():
    bot_token = os.environ['TELEGRAM_BOT_TOKEN']
    chat_id = os.environ['TELEGRAM_CHAT_ID']
    image_url = 'https://www.weather.gov/images/gsp/weatherstory.gif'
    
    eastern = ZoneInfo('America/New_York')
    now = datetime.now(eastern)
    
    # Check if it's 7:10 AM Eastern Time (within 30 minute window)
    if now.hour != 7 or now.minute >= 40:
        print(f"Current Eastern Time: {now.strftime('%H:%M')} - Not 7:10 AM ET, skipping.")
        return
    
    print(f"Current Eastern Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} - Sending weather image...")
    
    # Fetch the image
    response = requests.get(image_url)
    if response.status_code != 200:
        print(f"Failed to fetch image: {response.status_code}")
        return
    
    # Send via Telegram
    telegram_url = f'https://api.telegram.org/bot{bot_token}/sendPhoto'
    
    files = {'photo': ('weatherstory.gif', response.content, 'image/gif')}
    data = {
        'chat_id': chat_id,
        'caption': f'Daily Weather Story - {now.strftime("%B %d, %Y")}'
    }
    
    telegram_response = requests.post(telegram_url, files=files, data=data)
    
    if telegram_response.status_code == 200:
        print("Weather image sent successfully!")
    else:
        print(f"Failed to send image: {telegram_response.status_code}")
        print(telegram_response.text)

if __name__ == '__main__':
    send_weather_image()
