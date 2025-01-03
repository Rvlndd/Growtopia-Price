import os
from flask import Flask, request, jsonify
import requests
import re
import google.generativeai as genai
from fuzzywuzzy import fuzz
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

dis_search = "https://discord.com/api/v9/guilds/571992648190263317/messages/search"
dis_header = {
    "Authorization": os.getenv("DISCORD_AUTHORIZATION"),
    "Cookie": "__dcfduid=5beb9ea0b7d511efa06c211b7d074ae8; __sdcfduid=5beb9ea1b7d511efa06c211b7d074ae83f6ccdce918fdc171e548a2f463be0793d5e39354e1615876ad75f9c103dc74c",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"
}

genai.configure(api_key=os.getenv("GENAI_API_KEY"))
GEMINI_MODEL = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction="""kamu adalah ai untuk menentukan harga items, kalau hanya angka tanpa nama mata uang = 1 WL, 100 WL = 100 DL, = 100 DL = 1 BGL. 

Kamu akan meresponse dengan hanya response json seperti ini

json ( FOR TYPE: EACH)
Item_Name :
item price: (is the item price average from my input ) like If 1 bgl 50 dl 2 wl just show 15002 the item_price is price in WL (  100 WL = 100 DL, = 100 DL = 1 BGL.  ) LIKE IF ITS 1400 DLS show as 140000

REMINDER: ITEM_PRICE IS MUST AT WL FORMAT.

priceindl: 

PRICE IN DL IS LIKE formatted version If it has 150202 wls it show as 15 BGL 2 DL 2 WL don't add this is example

FOR TYPE: ( PER )
and if it has / its like howmuch items per wl itemprice is like example 200 or If the price is like 90/1 or smth like 5/1 is show the 5 at the item_price

IF THE TYPE IS PER, MAKE THE PRICEINDL IS NULL OR DO NOT ADD ANYTHING.

add json 

Type: each or per id per is item that has /, and each is item that the price is not have /



its average from my input also theres Many manipulators with unreasonable prices that exceed or decrease from the average price, don't add them up. 

The item name is from input itnm: Name

then after that is the price, theres like a mixed only took the exact persist the item name

BTW THE INPUT IS FROM DISCORD SEARCH!"""
)

def normalize_string(s):
    return re.sub(r"[^a-zA-Z0-9\s]", "", s).lower()

def search_fuzzy(item_name, line, threshold=80):
    normalized_item = normalize_string(item_name)
    normalized_line = normalize_string(line)
    return fuzz.partial_ratio(normalized_item, normalized_line) >= threshold

def format_price(wl_price):
    wl_price = int(wl_price)

    bgl = wl_price // 10000
    remaining = wl_price % 10000
    dl = remaining // 100
    wl = remaining % 100

    format_curr = []

    if bgl > 0:
        format_curr.append(f"{bgl} BGL")

    if dl > 0:
        format_curr.append(f"{dl} DL")

    if wl > 0:
        format_curr.append(f"{wl} WL")

    if not format_curr:
        return "0 WL"

    return " ".join(format_curr)

@app.route('/price', methods=['GET'])
def get_item_price():
    item_name = request.args.get('item', '')

    if not item_name:
        return jsonify({"error": "Item name is required"}), 400

    try:
        print(f"search : {item_name}") 

        params = {"content": item_name}
        response = requests.get(dis_search, headers=dis_header, params=params)

        print(f"Discord Response: {response.status_code}")
        if response.status_code != 200:
            return jsonify({"error": "discord error"}), 500

        data = response.json()

        filtered_results = set()
        for message in data.get('messages', []):
            content = message[0]['content']
            lines = content.split('\n')

            for line in lines:
                if re.search(r"(\d+(?:/\d+)?(?:\s?DL)?)", line):
                    if search_fuzzy(item_name, line, 80):
                        filtered_results.add(line)


        ai_calculate = f"itnm: {item_name}\n" + "\n".join(filtered_results)
        ai_res = GEMINI_MODEL.generate_content(ai_calculate)

        remjson = re.sub(r"^```json\n|\n```$", "", ai_res.text)


        try:
            price_data = json.loads(remjson)

            if price_data.get("Type") == "per":
                price_data["priceindl"] = None

        except json.JSONDecodeError as e:
            return jsonify({"error": "Invalid response"}), 500

        if price_data.get("priceindl") and price_data["priceindl"] is not None:
            price_data['priceindl'] = format_price(price_data['item_price'])

        return jsonify(price_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500        

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
          
