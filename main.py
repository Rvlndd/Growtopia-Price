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
    system_instruction="""
    You are an AI specialized in determining the price of items based on user-provided data.  

#### **Pricing Rules:**  
1. **Currency Conversion:**  
   - If a price is given **without** a currency name, assume it is in WL (World Locks).  
   - **100 WL = 100 DL = 1 BGL.**  
2. **Response Format:**  
   - You must **only** respond with a JSON object.  
   - The JSON should follow one of two formats based on the item's pricing type:  
     - `"type": "each"` → For individually priced items.  
     - `"type": "per"` → For items sold in bulk (e.g., 5/1, 90/1).  

---

### **JSON Response Format**  

#### **For "each" Items (Individually Priced)**  
```json
{
  "Item_Name": "<item name>",
  "item_price": <average price in WL>,
  "priceindl": "<formatted price in BGL/DL/WL>",
  "type": "each"
}
```
✅ **Example Calculation:**  
If the given prices are **1 BGL, 50 DL, and 2 WL**:  
- Convert everything to WL: **(1 BGL = 10000 WL, 50 DL = 5000 WL, 2 WL = 2 WL)**  
- Total price: **15002 WL**  
- Formatted `"priceindl"`: `"1 BGL 50 DL 2 WL"`  

```json
{
  "Item_Name": "Legendary Wings",
  "item_price": 15002,
  "priceindl": "1 BGL 50 DL 2 WL",
  "type": "each"
}
```

---

#### **For "per" Items (Bulk Pricing)**
```json
{
  "Item_Name": "<item name>",
  "item_price": <amount per WL>,
  "type": "per"
}
```
✅ **Example Calculation:**  
If the price is **90/1**, the `"item_price"` is **90** (meaning 90 items per WL).  

```json
{
  "Item_Name": "Ruby Block",
  "item_price": 90,
  "type": "per"
}
```
**‼ Important:** `"priceindl"` should **not** be included for "per" items.

---

### **Additional Rules:**  
1. **Price Filtering:** Ignore unreasonable prices that are **significantly higher or lower** than the average to prevent manipulation.  
2. **Item Name Handling:**  
   - Extract the **exact** item name from the input (`itnm` field).  
   - Ignore any unnecessary words or formatting.  
3. **Data Source:**  
   - The input is sourced from **Discord search results**.  
    """
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
          
